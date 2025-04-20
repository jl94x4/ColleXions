# Use an official Python runtime as a parent image
# Using slim-bullseye for a smaller image size based on Debian Bullseye
FROM python:3.12-slim-bullseye

# Set environment variables
# Ensures print statements and logs are sent straight to the terminal without buffering
ENV PYTHONUNBUFFERED=1

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# --no-cache-dir reduces image size, --upgrade pip ensures pip is recent
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the script into the container at /app
COPY collexions.py .

# Create the logs directory within the container (volume mount will overlay this)
RUN mkdir logs

# Define the command to run your script when the container starts
# This assumes collexions.py is in the root of /app
CMD ["python", "collexions.py"]