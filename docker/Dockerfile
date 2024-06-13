FROM python:3.11.5

WORKDIR /doc-gather
# copy project
COPY gather/ /doc-gather/gather
COPY *.py poetry.lock pyproject.toml entrypoint.sh ./
COPY prod.env local.env

# install poetry
# RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
RUN pip install --no-cache-dir poetry
# install poetry dependencies
RUN poetry config installer.max-workers 20
# RUN poetry install --no-root --no-dev
RUN poetry install --no-interaction --no-ansi -vvv --no-root --no-dev && \
    rm -rf /root/.cache/pypoetry/artifacts /root/.cache/pypoetry/cache
    
CMD ["./entrypoint.sh"]

