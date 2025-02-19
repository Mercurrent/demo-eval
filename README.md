# Evaluation Web-Service

This project is an evaluation web-service where data scientists can upload results of their model runs, upload and form test datasets, and run evaluations against them. The project uses Flask for the web server and supports both MongoDB and Azure Cosmos DB for storage.

## Features

- Create and define new use cases
- Upload label files for evaluation sets
- Automatically assign labels to gold and test sets
- Store evaluation sets and extraction results
- Generate evaluation reports

## Prerequisites

- Python 3.x
- MongoDB or Azure Cosmos DB Emulator
- Poetry (for dependency management)

## Installation

1. **Clone the repository**:
   ```sh
   git clone https://gitlab.dx1.lseg.com/app/app-52495/extraction-evaluation.git
   cd extraction-evaluation
   ```

2. **Install dependencies using Poetry**:
   ```sh
   poetry install
   ```

3. **Configure Database Connection**:
   Create a `.env` file in the project root with your database connection string:
   ```
   # For MongoDB
   DB_CONNECTION_STRING=mongodb://localhost:27017/

   # For Cosmos DB Emulator
   DB_CONNECTION_STRING=mongodb://localhost:C2y6yDjf5%2FR%2Bob0N8A7Cgv30VRDJIWEHLM%2B4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw%2FJw%3D%3D@localhost:10255/admin?ssl=true
   ```

4. **Start your database**:
   Either start MongoDB:
   ```sh
   brew services start mongodb-community
   ```
   Or start the Cosmos DB Emulator from the Azure portal

5. **Run the FastAPI application**:
   ```sh
   poetry run uvicorn app:app --reload
   ```

## Usage

1. **Access the application**:
   Open your web browser and navigate to `http://127.0.0.1:5000/use_cases`

2. **Create a new use case**:
   - Navigate to `http://127.0.0.1:5000/create_use_case.html`
   - Fill in the use case name and success criteria, then click "Create"

3. **Upload a label file**:
   - Navigate to `http://127.0.0.1:5000/upload_label_file.html`
   - Enter the use case ID and select the label file to upload, then click "Upload"

4. **View an evaluation report**:
   - Navigate to `http://127.0.0.1:5000/view_report.html`
   - Enter the evaluation iteration ID to view the report

## Project Structure

- `app.py`: The main Flask application file
- `pyproject.toml`: Poetry dependencies and project configuration
- `.env`: Database configuration (not in version control)
- `templates/`: Directory containing HTML templates
  - `index.html`: Home page
  - `create_use_case.html`: Page for creating a new use case
  - `upload_label_file.html`: Page for uploading a label file
  - `view_report.html`: Page for viewing an evaluation report

