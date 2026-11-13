FROM python:3.13-slim
RUN pip install --no-cache-dir Pillow==11.3.0
WORKDIR /app
COPY quiz/ ./quiz/
COPY import/ ./import/
ENV PYTHONUNBUFFERED=1
EXPOSE 18770
CMD ["python", "quiz/server.py", "--host", "0.0.0.0", "--port", "18770", "--no-browser"]
