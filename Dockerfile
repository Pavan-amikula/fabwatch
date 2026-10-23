FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
RUN python -m fabwatch.train && cp reports/evaluation.png web/evaluation.png
EXPOSE 8000
CMD ["uvicorn","fabwatch.api:create_app","--factory","--host","0.0.0.0","--port","8000"]
