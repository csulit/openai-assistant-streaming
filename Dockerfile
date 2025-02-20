FROM python:3.13.2

# Set the working directory
WORKDIR /app

# Install system dependencies for ODBC and Microsoft ODBC Driver for SQL Server
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    unixodbc \
    unixodbc-dev \
    apt-transport-https \
    libssl3  # Use libssl3 instead of libssl1.1

# Add Microsoft repository and install the ODBC Driver
RUN curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | tee /etc/apt/trusted.gpg.d/microsoft.asc > /dev/null && \
    curl -fsSL https://packages.microsoft.com/config/debian/11/prod.list | tee /etc/apt/sources.list.d/mssql-release.list > /dev/null && \
    apt-get update && ACCEPT_EULA=Y apt-get install -y \
    msodbcsql18

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files
COPY . .

# Run the application
CMD ["python", "main.py"]
