FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

# ✅ FORCE CLEAN INSTALL (no cache issue)
RUN rm -rf /ms-playwright

# ✅ INSTALL ALL BROWSERS PROPERLY
RUN playwright install --with-deps chromium

# ✅ VERIFY INSTALL (important)
RUN ls -la /ms-playwright

EXPOSE 8080

CMD ["streamlit", "run", "app.py", "--server.port=8080", "--server.address=0.0.0.0"]
