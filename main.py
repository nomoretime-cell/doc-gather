import string
import threading
from pyfunvice import (
    app_service,
    start_app,
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
        try:
            doc_info = routeInfo.uuid.split("_")

            self.doc_id = doc_info[0]
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
        except Exception as e:
            print(e)
            raise e


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
            print(f"Page [{str(type_block.page_index)}] is Completed")

    def is_completed(self):
        return len(self.type_blocks) == self.type_block_num


class DocWrapper:
    def __init__(self, page_num):
        self.page_num = page_num
        self.pages: dict[int, PageWrapper] = {}

    def insert_type_block(self, type_block: TypeBlock):
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
    try:
        print(routeInfo)
        routeInfo = RouteInfo(**routeInfo)
        type_block = TypeBlock(routeInfo, data)

        global docs
        with lock:
            if type_block.doc_id not in docs:
                docs[type_block.doc_id] = DocWrapper(type_block.page_num)
            docs[type_block.doc_id].insert_type_block(type_block)
            if docs[type_block.doc_id].is_completed():
                print(f"Doc [{str(type_block.doc_id)}] is Completed")
                pages: list[Page] = []
                doc: DocWrapper = docs[type_block.doc_id]
                for p_i in range(doc.page_num):
                    page_wrapper: PageWrapper = doc.pages[p_i]
                    
                    # get text from blocks
                    block_idx_2_text: dict[int, str] = {}
                    for type_block in page_wrapper.type_blocks.values():
                        if type_block.type != "text":
                            block_idx_2_text[type_block.block_index] = type_block.data_object
                    
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
                with open(f"{type_block.doc_id}.md", "w") as file:
                    file.write(text)
                del docs[type_block.doc_id]
                return {"text": "none"}
    except Exception as e:
        print(e)
        raise e


if __name__ == "__main__":
    start_app(workers=1, port=8005, post_fork_func=None)
