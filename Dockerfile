# One image: build the React app, serve it and the API from FastAPI on $PORT.
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY core/ core/
COPY api/ api/
COPY cache/ cache/
COPY data/ data/
COPY supplier_risk_dataset.csv risk_criteria_description.md ./
COPY --from=web /web/dist web/dist
ENV PORT=8000
# Deployed image always runs on Nebius; local dev uses LLM_PROVIDER=claude from .env
ENV LLM_PROVIDER=nebius
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
