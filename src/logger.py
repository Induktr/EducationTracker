import logging
import sys
from datetime import datetime
from typing import Dict, Any

class JobSearchLogger:
    def __init__(self):
        self.logger = logging.getLogger("job_search")
        self.logger.setLevel(logging.INFO)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

    def log_job_processing(self, job_id: str, status: str, details: Dict[str, Any]) -> None:
        """Log job processing events"""
        self.logger.info(f"Job {job_id} - Status: {status} - Details: {details}")

    def log_error(self, error_type: str, error_message: str, details: Dict[str, Any]) -> None:
        """Log errors during processing"""
        self.logger.error(f"Error: {error_type} - Message: {error_message} - Details: {details}")

    def log_api_call(self, api_name: str, endpoint: str, status: str) -> None:
        """Log API calls"""
        self.logger.info(f"API Call: {api_name} - Endpoint: {endpoint} - Status: {status}")

logger = JobSearchLogger()
