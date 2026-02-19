FROM python:3.12-slim

# Run as a non-root user to limit blast radius if the process is compromised
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

COPY requirements.txt .

# Install with hash verification — pip will reject any package whose hash
# does not match what is recorded in requirements.txt
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

COPY --chown=appuser:appgroup src/ ./src/

USER appuser

CMD ["python", "src/main.py"]
