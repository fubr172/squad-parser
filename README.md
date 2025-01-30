# Log Processing Tool

This project is a log processing tool that reads and analyzes game logs in real-time. It extracts various events from the logs using regular expressions and formats them into human-readable strings. The tool can handle multiple log files simultaneously and can be run in a new console window.

## Features

- **Real-time log processing**: Continuously reads new lines from the log files.
- **Event parsing**: Uses regular expressions to match and extract information about various game events such as damage received, player deaths, and connections.
- **Formatted output**: Converts raw log data into structured, human-readable messages.
- **Automatic channel management**: Can create or delete voice channels based on user interactions (if integrated).

## Code Overview

### Main Components

1. **Patterns Dictionary**: Contains regular expressions for matching different types of log entries.
2. **`format_event` Function**: Formats matched log entries into readable strings.
3. **`LogProcessor` Class**: Handles reading from log files and processing the logs.
   - `read_existing_lines()`: Reads all lines from the file at startup.
   - `tail_file()`: Asynchronously reads new lines added to the file.
   - `run()`: Processes existing and new log entries in real-time.

4. **Log Processing Functions**:
   - `process_log_in_real_time(file_path)`: Processes a specified log file in real-time.
   - `process_multiple_files(files)`: Processes multiple log files concurrently.
   - `process_file_in_new_console(file_path)`: Launches processing of a specified log file in a new console window.

## Requirements

- Python 3.7 or higher
- Required libraries:
  - `discord.py`
  - `aiofiles`
  - Any other dependencies specified in your environment.

## Usage

1. Clone the repository:
git clone <repository-url>
cd <repository-directory>
text

2. Install the required packages:
pip install -r requirements.txt
text

3. Run the script:
python <script-name>.py
text

4. To process a specific log file in real-time, you can call:
await process_log_in_real_time('path/to/logfile.log')
text

5. To process multiple files concurrently:
await process_multiple_files(['path/to/logfile1.log', 'path/to/logfile2.log'])
text

6. To run the processing in a new console window:
process_file_in_new_console('path/to/logfile.log')
text

## Logging

The tool uses Python's built-in logging module to log information, warnings, and errors. Ensure that logging is configured to your desired level (e.g., INFO, WARNING, ERROR).

## Contributing

Feel free to fork the repository and submit pull requests for any improvements or bug fixes.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
