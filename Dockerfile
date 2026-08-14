# Fiction Academy — 通用容器镜像（ClawCloud / HF Spaces / 任何 Docker 平台）
FROM python:3.13-slim

WORKDIR /app

# 先装依赖（利用层缓存）
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# 应用代码与静态资源（前端只带构建产物）
COPY backend backend
COPY characters characters
COPY frontend-vue/dist frontend-vue/dist

# 运行时数据目录（平台上请把持久卷挂到 /app/data）
RUN mkdir -p /app/data /app/logs
ENV FA_DATABASE_PATH=/app/data/fiction_academy.db

# LLM_API_KEY / LLM_BASE_URL / FA_DEFAULT_MODEL 通过平台环境变量注入，不要写进镜像
EXPOSE 8000
CMD ["sh", "-c", "python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
