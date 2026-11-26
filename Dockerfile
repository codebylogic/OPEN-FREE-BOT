FROM python:3.12-slim

# opencode ke liye node + git + curl
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates git unzip nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# opencode CLI (free models isi client ke andar chalta hai)
RUN curl -fsSL https://opencode.ai/install | bash || npm install -g opencode-ai
ENV PATH="/root/.opencode/bin:/root/.local/bin:${PATH}"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

# kaam karne ke liye jagah
RUN mkdir -p /workspace /app/data
ENV OPENCODE_WORKDIR=/workspace \
    STATE_DB=/app/data/state.db \
    PYTHONUNBUFFERED=1

# webhook mode (Render/Koyeb) ke liye; polling mode me port use nahi hota
EXPOSE 8080

CMD ["python", "bot.py"]
