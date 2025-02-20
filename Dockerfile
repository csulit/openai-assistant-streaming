FROM python:3.13.2

# Set the working directory
WORKDIR /app

# Install system dependencies for ODBC
RUN apt-get update && apt-get install -y unixodbc unixodbc-dev

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files
COPY . .

# Run the application
CMD ["python", "main.py"]
