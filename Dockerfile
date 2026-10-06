FROM python:3.12-slim
WORKDIR /work
COPY minilite.py README.md ./
COPY steps/ ./steps/
COPY demos/ ./demos/
COPY experiments/ ./experiments/
COPY tests/ ./tests/
CMD ["python3","tests/test_minilite.py"]
