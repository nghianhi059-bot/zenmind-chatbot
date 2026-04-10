# --- GIAI ĐOẠN 1: CHẠY KIỂM THỬ (TESTER) ---
FROM python:3.10-slim as tester
WORKDIR /app

# Cài đặt công cụ hệ thống và thư viện (bao gồm cả thư viện test)
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt pytest httpx

COPY . .
# Chạy lệnh test. Nếu có lỗi, quá trình Build sẽ dừng ngay tại đây!
RUN pytest tests/

# --- GIAI ĐOẠN 2: ĐÓNG GÓI SẢN PHẨM THỰC TẾ (FINAL) ---
FROM python:3.10-slim as final
WORKDIR /app

RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
