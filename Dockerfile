# Use the official lightweight Python image from the Docker Hub.
# This provides a clean, minimal foundation.
FROM python:3.9-slim

# Set the working directory inside the container to /app.
# All subsequent commands will run from this directory.
WORKDIR /app

# Copy our requirements file into the container.
COPY requirements.txt requirements.txt

# Install the Python dependencies defined in the requirements file.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of our application's source code into the container.
COPY . .

# Tell the container to listen for incoming web traffic on port 8080.
# The PORT environment variable will be set by Cloud Run.
EXPOSE 8080

# The command to run when the container starts. This executes our Flask app.
CMD ["python", "main.py"]