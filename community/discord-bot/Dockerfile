FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /bot
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py config.py ./
RUN useradd --system --uid 10001 lightning
USER lightning
CMD ["python", "bot.py"]
