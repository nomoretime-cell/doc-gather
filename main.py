import datetime
import logging
import os
import string
import threading
import time
from pyfunvice import (
    app_service,
    start_app,
    app_service_get,
)

from gather.bullets import replace_bullets
from gather.headers import filter_common_titles
from gather.markdown import get_string, merge_lines, merge_spans
from gather.schema import (
    FullyMergedBlock,
    Line,
    MergedBlock,
    Page,
    RouteInfo,
    Span,
)
import re
import requests

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] [%(thread)d] [%(levelname)s] %(message)s"
)


def generate_markdown(pages: list[Page]) -> string:
    if len(pages) == 0:
        return ""
    # Copy to avoid changing original data
    merged_pages: list[list[MergedBlock]] = merge_spans(pages)
    merged_blocks: list[FullyMergedBlock] = merge_lines(merged_pages, pages)
    merged_blocks = filter_common_titles(merged_blocks)
    pages_string: str = get_string(merged_blocks)

    # Handle empty blocks being joined
    pages_string = re.sub(r"\n{3,}", "\n\n", pages_string)
    pages_string = re.sub(r"(\n\s){3,}", "\n\n", pages_string)

    # Replace bullet characters with a -
    pages_string = replace_bullets(pages_string)
    return pages_string


class TypeBlock:
    def __init__(self, routeInfo: RouteInfo, data):
        doc_info = routeInfo.uuid.split("_")

        self.doc_id = doc_info[0].replace("/", "_")
        self.page_index = int(doc_info[1])
        self.page_num = int(doc_info[2])
        self.type_block_index = int(doc_info[3])
        self.type_block_num = int(doc_info[4])
        self.block_index = int(doc_info[5])
        self.type = routeInfo.type

        if routeInfo.type == "text":
            self.data_object = Page(**data)
        elif routeInfo.type == "equation":
            self.data_object = data["text"]
        elif routeInfo.type == "table":
            self.data_object = data["text"]
        elif routeInfo.type == "picture":
            self.data_object = ""
        else:
            raise Exception(f"Unknown type: {routeInfo.type}")


class PageWrapper:
    def __init__(self, type_block_num):
        self.type_block_num = type_block_num
        self.type_blocks: dict[int, TypeBlock] = {}
        self.page_instance: Page = None

    def insert_type_block(self, type_block: TypeBlock):
        if type_block.type_block_index not in self.type_blocks:
            self.type_blocks[type_block.type_block_index] = type_block
        if type_block.type == "text":
            self.page_instance = type_block.data_object
        if self.is_completed():
            logging.info(f"Page [{str(type_block.page_index)}] is Completed")

    def is_completed(self):
        return len(self.type_blocks) == self.type_block_num


class DocWrapper:
    def __init__(self, page_num):
        self.page_num = page_num
        self.pages: dict[int, PageWrapper] = {}
        self.last_update = datetime.datetime.now()

    def insert_type_block(self, type_block: TypeBlock):
        self.last_update = datetime.datetime.now()
        if type_block.page_index not in self.pages:
            self.pages[type_block.page_index] = PageWrapper(type_block.type_block_num)
        self.pages[type_block.page_index].insert_type_block(type_block)

    def is_completed(self):
        for page in self.pages.values():
            if not page.is_completed():
                return False
        return len(self.pages) == self.page_num


docs: dict[str, DocWrapper] = {}
lock = threading.Lock()


@app_service(path="/api/v1/parser/ppl/gather", inparam_type="flat")
async def process(routeInfo: RouteInfo, data):
    logging.info(
        "POST request"
        + f" [P{os.getpid()}][T{threading.current_thread().ident}] "
        + f"routeInfo: {routeInfo}"
    )
    routeInfo = RouteInfo(**routeInfo)
    type_block = TypeBlock(routeInfo, data)

    global docs
    with lock:
        if type_block.doc_id not in docs:
            docs[type_block.doc_id] = DocWrapper(type_block.page_num)
        docs[type_block.doc_id].insert_type_block(type_block)
        if docs[type_block.doc_id].is_completed():
            process_completed_doc(type_block.doc_id)
        return {"text": "none"}

def process_completed_doc(doc_id):
    logging.info(f"Doc [{str(doc_id)}] is Completed")
    pages: list[Page] = []
    doc: DocWrapper = docs[doc_id]
    for p_i in range(doc.page_num):
        page_wrapper: PageWrapper = doc.pages[p_i]

        # get text from blocks
        block_idx_2_text: dict[int, str] = {}
        for type_block in page_wrapper.type_blocks.values():
            if type_block.type != "text":
                block_idx_2_text[type_block.block_index] = (
                    type_block.data_object
                )

        # fill blocks
        page_instance: Page = page_wrapper.page_instance
        for block_idx, text in block_idx_2_text.items():
            page_instance.blocks[block_idx].lines = [
                Line(
                    bbox=page_instance.blocks[block_idx].bbox,
                    spans=[
                        Span(
                            bbox=page_instance.blocks[block_idx].bbox,
                            span_id="test",
                            font="test",
                            color=0,
                            block_type="test",
                            text=f"{text}",
                        )
                    ],
                )
            ]
        pages.append(page_instance)
    text = generate_markdown(pages)
    markdown_file_name = f"{type_block.doc_id}.md"
    # upload_file(routeInfo.key, markdown_file_name, text)
    save_file(markdown_file_name, text)
    logging.info(f"Doc [{str(type_block.doc_id)}] Saved Completed")
    del docs[type_block.doc_id]

def save_file(markdown_file_name, text):
    mount_path = os.environ.get("MOUNT_PATH")
    file_path = os.path.join(mount_path, markdown_file_name)
    with open(file_path, "w") as file:
        file.write(text)


def upload_file(channelId, file_name, text):
    with open(file_name, "w") as file:
        file.write(text)
    r = requests.post(
        "http://127.0.0.1:3031/tasklet/service/oss",
        files={"file": open(file_name, "rb")},
        data={"channelId": channelId},
    )
    if r.status_code != 200:
        raise Exception(f"Upload file failed: {r.text}")
    os.remove(file_name)


@app_service_get(path="/health")
async def health(data: dict) -> dict:
    time_string = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {"timestamp": time_string}

def check_timeout():
    while True:
        now = datetime.datetime.now()
        to_process = []
        
        with lock:
            for doc_id, doc in docs.items():
                if now - doc.last_update > datetime.datetime.timedelta(minutes=5):
                    to_process.append(doc_id)
        
        for doc_id in to_process:
            process_completed_doc(doc_id)
        time.sleep(10)
if __name__ == "__main__":
    new_thread = threading.Thread(target=check_timeout)
    new_thread.start()
    start_app(workers=1, port=8000, post_fork_func=None)
