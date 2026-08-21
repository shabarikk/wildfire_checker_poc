FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# GOA CA cert — required for HTTPS connections to gateway/Ent Tools from Cloud Run
COPY goa-ca-chain.pem /usr/local/share/ca-certificates/goa-ca.crt
RUN update-ca-certificates
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

EXPOSE 8080
CMD ["python", "app.py"]
