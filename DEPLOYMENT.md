# Deployment

This app cannot run on GitHub Pages because it needs Python, Streamlit, Playwright, Chromium, and Google Sheets credentials. Use GitHub for the code and a web app host such as Render, Railway, Fly.io, or a VPS for the running app.

## Recommended: Render

1. Push this repo to GitHub.
2. In Render, create a new Blueprint or Web Service from the GitHub repo.
3. Use the included `Dockerfile`; it installs Python dependencies and Chromium for Playwright.
4. Add the environment variable `GOOGLE_CREDENTIALS_JSON` with the full JSON content from your local `credentials.json`.
5. Deploy the service.
6. Add your custom domain in Render's Custom Domains settings, then update your domain DNS as Render instructs.

Keep `credentials.json` out of GitHub. It is already ignored locally and is also excluded from the Docker image.
