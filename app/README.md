# Gaming Center Management System

A modern desktop application for managing gaming centers/internet cafes, built with Python and PySide6.

## Features

- Central server application for managing all computers
- Client application for individual computers
- Session management and time tracking
- Multiple tariff support
- Payment processing
- Session history and reporting
- Network discovery of clients
- System lockdown capabilities

## Requirements

- Python 3.8+
- PySide6
- SQLite3
- Other dependencies listed in requirements.txt

## Installation

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Project Structure

```
.
├── client/             # Client application
│   ├── src/           # Source code
│   └── resources/     # Resources (icons, etc.)
├── server/            # Server application
│   ├── src/          # Source code
│   ├── resources/    # Resources
│   └── database/     # Database files
└── requirements.txt   # Project dependencies
```

## Usage

1. Start the server application:
   ```bash
   python server/src/main.py
   ```

2. Start the client application on each computer:
   ```bash
   python client/src/main.py
   ```

## License

MIT License 