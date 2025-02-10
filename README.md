# Evaluation Web-Service

This project is an evaluation web-service where data scientists can upload results of their model runs, upload and form test datasets, and run evaluations against them. The project uses Flask for the web server and MongoDB for storage.

## Features

- Create and define new use cases
- Upload label files for evaluation sets
- Automatically assign labels to gold and test sets
- Store evaluation sets and extraction results
- Generate evaluation reports

## Prerequisites

- Python 3.x
- MongoDB

## Installation

1. **Clone the repository**:
   ```sh
   git clone https://github.com/yourusername/Demo-LSEG.git
   cd Demo-LSEG
   ```

2. **Install the required dependencies**:
   ```sh
   pip install -r requirements.txt
   ```

3. **Start the MongoDB server**:
   Ensure MongoDB is installed and running on your system.

   For Mac:

   ```sh
   brew tap mongodb/brew
   brew install mongodb-community

   brew services start mongodb-community
   ```

4. **Run the Flask application**:

   ```sh
   export FLASK_APP=app.py
   export FLASK_ENV=development
   flask run
   ```

   Alternatively, you can run the application directly using Python:

   ```sh
   python app.py
   ```

## Usage

1. **Access the application**:
   Open your web browser and navigate to `http://127.0.0.1:5000/` to access the home page of the evaluation web-service.

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
- `requirements.txt`: List of required Python packages
- `templates/`: Directory containing HTML templates
  - `index.html`: Home page
  - `create_use_case.html`: Page for creating a new use case
  - `upload_label_file.html`: Page for uploading a label file
  - `view_report.html`: Page for viewing an evaluation report

## License

This project is licensed under the MIT License.
