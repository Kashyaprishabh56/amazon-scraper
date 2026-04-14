FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

# 🔥 force clean install (remove broken cache)
RUN rm -rf /root/.cache/ms-playwright
RUN rm -rf /ms-playwright

# 🔥 install browsers in correct location
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install chromium

# 🔥 debug (you should see chromium files in logs)
RUN ls -la /ms-playwright

EXPOSE 8080

CMD ["streamlit", "run", "app.py", "--server.port=8080", "--server.address=0.0.0.0"]
