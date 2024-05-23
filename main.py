import json
import string
from pyfunvice import (
    app_service,
    start_app,
)

from gather.bullets import replace_bullets
from gather.headers import filter_common_titles
from gather.markdown import get_string, merge_lines, merge_spans
from gather.schema import EquationInfo, FullyMergedBlock, GatherData, MergedBlock, Page, PictureInfo, RouteInfo, TableInfo
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


@app_service(path="/api/v1/parser/ppl/gather", inparam_type="flat")
async def process(routeInfo: RouteInfo, data):
    routeInfo = RouteInfo(**routeInfo)
    
    doc_info = routeInfo.uuid.split("_")
    doc_id = doc_info[0]
    page_index = int(doc_info[1])
    page_num = int(doc_info[2])
    type_block_index = int(doc_info[3])
    type_block_num = int(doc_info[4])
    block_index = int(doc_info[5])
    
    if routeInfo.type == "text":
        data_object = Page(**data)
        pass
    elif routeInfo.type == "equation":
        data_object = EquationInfo(**data)
        pass
    elif routeInfo.type == "table":
        data_object = TableInfo(**data)
        pass
    elif routeInfo.type == "picture":
        data_object = PictureInfo(**data)
        pass
    
    pages: list[Page] = [] 
    text = generate_markdown(pages)
    return {"text": text}


if __name__ == "__main__":
    start_app(workers=1, port=8005, post_fork_func=None)
