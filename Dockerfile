FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

# install browsers properly
RUN playwright install --with-deps

EXPOSE 8080

CMD ["streamlit", "run", "app.py", "--server.port=8080", "--server.address=0.0.0.0"]
