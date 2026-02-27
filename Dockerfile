FROM python:3.12

# Instala Tesseract e as bibliotecas de sistema para OpenCV
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY . .

# Inicia a API
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]