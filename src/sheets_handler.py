import logging
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from typing import List, Dict, Any
import json
from datetime import datetime, timezone
from config import GOOGLE_SHEETS_CREDENTIALS, SHEET_ID, JOBS_WORKSHEET, LOGS_WORKSHEET
from logger import logger
from utils import validate_job_data, deduplicate_jobs

class GoogleSheetsHandler:
    def __init__(self):
        if not GOOGLE_SHEETS_CREDENTIALS:
            raise ValueError("Google Sheets credentials not found in environment variables")

        try:
            credentials_dict = json.loads(GOOGLE_SHEETS_CREDENTIALS)
            credentials = Credentials.from_service_account_info(
                credentials_dict,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            self.service = build('sheets', 'v4', credentials=credentials)
            self.sheet_id = SHEET_ID

            # Create worksheets if they don't exist
            self._ensure_worksheet_exists(JOBS_WORKSHEET)
            self._ensure_worksheet_exists(LOGS_WORKSHEET)
            # Create headers if they don't exist
            self._ensure_headers()
            # Apply conditional formatting
            self.apply_conditional_formatting()

            logger.log_job_processing(
                "sheets_init",
                "success",
                {"sheet_id": SHEET_ID}
            )

        except Exception as e:
            logger.log_error(
                "sheets_init_error",
                str(e),
                {"credentials_type": type(credentials_dict).__name__ if 'credentials_dict' in locals() else 'not_created'}
            )
            raise

    def _ensure_worksheet_exists(self, worksheet_name: str):
        """Ensure the worksheet exists, create if it doesn't"""
        try:
            # Get spreadsheet metadata
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=self.sheet_id
            ).execute()

            # Check if worksheet exists
            sheets = spreadsheet.get('sheets', [])
            sheet_exists = any(
                sheet['properties']['title'] == worksheet_name
                for sheet in sheets
            )

            if not sheet_exists:
                # Create new worksheet
                requests = [{
                    'addSheet': {
                        'properties': {
                            'title': worksheet_name,
                            'gridProperties': {
                                'rowCount': 1000,
                                'columnCount': 12
                            }
                        }
                    }
                }]

                self.service.spreadsheets().batchUpdate(
                    spreadsheetId=self.sheet_id,
                    body={'requests': requests}
                ).execute()

                logger.log_job_processing(
                    "worksheet_created",
                    "success",
                    {"worksheet": worksheet_name}
                )

        except Exception as e:
            logger.log_error(
                "worksheet_create_error",
                str(e),
                {"worksheet": worksheet_name}
            )
            raise

    def append_jobs(self, jobs: List[Dict[str, Any]]) -> None:
        """Append new jobs to the Google Sheet"""
        try:
            if not jobs:
                logger.log_job_processing(
                    "sheets_append",
                    "skipped",
                    {"reason": "no_jobs_provided"}
                )
                return

            logger.log_job_processing(
                "sheets_append_start",
                "starting",
                {"total_jobs": len(jobs)}
            )

            # Get existing job IDs to avoid duplicates
            existing_ids = self.get_existing_job_ids()
            unique_jobs = deduplicate_jobs(jobs, existing_ids)

            values = []
            for job in unique_jobs:
                # Validate job data
                if not validate_job_data(job):
                    logger.log_error(
                        "invalid_job_data",
                        "Missing required fields",
                        {"job_id": job.get("job_id")}
                    )
                    continue

                try:
                    row = [
                        str(job.get("job_id", "")),
                        str(job.get("title", "")),
                        str(job.get("company", "")),
                        str(job.get("location", "")),
                        str(job.get("description", ""))[:500],  # Limit description length
                        str(job.get("experience_level", "")),
                        str(job.get("salary_from", "")),
                        str(job.get("salary_to", "")),
                        str(job.get("salary_currency", "")),
                        str(job.get("apply_url", "")),
                        job.get("posted_at", datetime.now(timezone.utc).isoformat()),
                        datetime.now(timezone.utc).isoformat()
                    ]
                    values.append(row)
                except Exception as row_e:
                    logger.log_error(
                        "row_formatting_error",
                        str(row_e),
                        {"job_id": job.get("job_id")}
                    )
                    continue

            if not values:
                logger.log_job_processing(
                    "sheets_append",
                    "skipped",
                    {"reason": "no_valid_jobs"}
                )
                return

            # Log the data we're about to write
            logger.log_job_processing(
                "sheets_append_data",
                "preparing",
                {
                    "jobs_count": len(values),
                    "example_job": {
                        "id": values[0][0],
                        "title": values[0][1]
                    } if values else None
                }
            )

            body = {'values': values}
            try:
                result = self.service.spreadsheets().values().append(
                    spreadsheetId=self.sheet_id,
                    range=f"{JOBS_WORKSHEET}!A2",  # Start after header
                    valueInputOption='RAW',
                    insertDataOption='INSERT_ROWS',
                    body=body
                ).execute()

                logger.log_job_processing(
                    "sheets_append",
                    "success",
                    {
                        "rows_added": len(values),
                        "update_range": result.get('updates', {}).get('updatedRange', ''),
                        "updated_rows": result.get('updates', {}).get('updatedRows', 0)
                    }
                )
            except Exception as inner_e:
                logger.log_error(
                    "sheets_append_operation_error",
                    str(inner_e),
                    {"job_count": len(values)}
                )
                raise

        except Exception as e:
            logger.log_error(
                "sheets_append_error",
                str(e),
                {"job_count": len(jobs) if jobs else 0}
            )
            raise

    def get_existing_job_ids(self) -> List[str]:
        """Get list of existing job IDs to avoid duplicates"""
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=f"{JOBS_WORKSHEET}!A:A"
            ).execute()

            values = result.get('values', [])
            # Skip header row and extract job IDs
            ids = [row[0] for row in values[1:] if row]

            logger.log_job_processing(
                "sheets_get_ids",
                "success",
                {"found_ids_count": len(ids)}
            )

            return ids

        except HttpError as e:
            logger.log_error(
                "sheets_get_ids_error",
                str(e),
                {}
            )
            return []  # Возвращаем пустой список вместо вызова исключения

    def get_existing_job_data(self) -> Dict[str, Dict[str, Any]]:
        """Get more complete data about existing jobs for better deduplication"""
        try:
            # Получаем больше данных для более надежной дедупликации:
            # ID, название, компанию, локацию, описание, зарплату
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=f"{JOBS_WORKSHEET}!A:J"  # Колонки до J (включая описание и зарплату)
            ).execute()

            values = result.get('values', [])
            if not values or len(values) <= 1:  # Только заголовки или пусто
                return {}

            # Пропускаем заголовок (строка 1)
            job_data = {}
            for row in values[1:]:
                if len(row) >= 4:  # Убедимся, что основные данные есть
                    job_id = row[0]
                    job_data[job_id] = {
                        'title': row[1].lower().strip() if len(row) > 1 else '',
                        'company': row[2].lower().strip() if len(row) > 2 else '',
                        'location': row[3].lower().strip() if len(row) > 3 else '',
                        'description': row[4] if len(row) > 4 else '',
                        'experience_level': row[5] if len(row) > 5 else '',
                        'salary_from': row[6] if len(row) > 6 else '',
                        'salary_to': row[7] if len(row) > 7 else '',
                        'salary_currency': row[8] if len(row) > 8 else '',
                        'apply_url': row[9] if len(row) > 9 else ''
                    }

            logger.log_job_processing(
                "sheets_get_job_data",
                "success",
                {"found_jobs_count": len(job_data), "data_fields": ["title", "company", "location", "description", "salary"]}
            )

            return job_data

        except HttpError as e:
            logger.log_error(
                "sheets_get_job_data_error",
                str(e),
                {}
            )
            return {}

    def _ensure_headers(self):
        """Ensure headers exist in the Jobs worksheet"""
        try:
            # Define headers
            headers = [
                "ID", "Название", "Компания", "Локация", "Описание",
                "Уровень", "Зарплата от", "Зарплата до", "Валюта",
                "Ссылка", "Дата публикации", "Дата обработки"
            ]

            # Get current headers
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=f"{JOBS_WORKSHEET}!A1:L1"
            ).execute()

            if not result.get('values'):
                # Add headers if they don't exist
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.sheet_id,
                    range=f"{JOBS_WORKSHEET}!A1:L1",
                    valueInputOption='RAW',
                    body={'values': [headers]}
                ).execute()

                logger.log_job_processing(
                    "headers_created",
                    "success",
                    {"headers": headers}
                )

        except Exception as e:
            logger.log_error(
                "headers_create_error",
                str(e),
                {}
            )
            raise

    def apply_conditional_formatting(self):
        """Apply conditional formatting rules to the sheet"""
        try:
            # Get the sheet ID first
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=self.sheet_id
            ).execute()

            sheet_id = None
            for sheet in spreadsheet.get('sheets', []):
                if sheet['properties']['title'] == JOBS_WORKSHEET:
                    sheet_id = sheet['properties']['sheetId']
                    break

            if sheet_id is None:
                logger.log_error(
                    "conditional_formatting_error",
                    "Sheet not found",
                    {"worksheet": JOBS_WORKSHEET}
                )
                return

            # Formatting rules
            requests = [
                # Format None values in salary columns
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 6, "endColumnIndex": 8}],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_CONTAINS",
                                    "values": [{"userEnteredValue": "None"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 1, "green": 0.8, "blue": 0.8},
                                    "textFormat": {"foregroundColor": {"red": 0, "green": 0, "blue": 0}}
                                }
                            }
                        }
                    }
                },
                # Format Junior level (фиолетовый)
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 5, "endColumnIndex": 6}],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_EQ",
                                    "values": [{"userEnteredValue": "junior"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 0.8, "green": 0.6, "blue": 0.9},
                                    "textFormat": {"foregroundColor": {"red": 0, "green": 0, "blue": 0}}
                                }
                            }
                        }
                    }
                },
                # Format Middle level (жёлтый)
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 5, "endColumnIndex": 6}],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_EQ",
                                    "values": [{"userEnteredValue": "middle"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 1, "green": 0.9, "blue": 0.4},
                                    "textFormat": {"foregroundColor": {"red": 0, "green": 0, "blue": 0}}
                                }
                            }
                        }
                    }
                },
                # Format Senior level (зелёный)
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 5, "endColumnIndex": 6}],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_EQ",
                                    "values": [{"userEnteredValue": "senior"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 0.5, "green": 0.9, "blue": 0.5},
                                    "textFormat": {"foregroundColor": {"red": 0, "green": 0, "blue": 0}}
                                }
                            }
                        }
                    }
                },
                # Format high RUB salaries
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 6, "endColumnIndex": 8}],
                            "booleanRule": {
                                "condition": {
                                    "type": "NUMBER_GREATER_THAN_EQ",
                                    "values": [{"userEnteredValue": "40000"}]
                                },
                                "format": {"backgroundColor": {"red": 0.7, "green": 0.9, "blue": 0.7}}
                            }
                        }
                    }
                },
                # Format medium RUB salaries
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 6, "endColumnIndex": 8}],
                            "booleanRule": {
                                "condition": {
                                    "type": "NUMBER_BETWEEN",
                                    "values": [
                                        {"userEnteredValue": "30000"},
                                        {"userEnteredValue": "40000"}
                                    ]
                                },
                                "format": {"backgroundColor": {"red": 1, "green": 1, "blue": 0.7}}
                            }
                        }
                    }
                },
                # Format USD in currency column
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 8, "endColumnIndex": 9}],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_EQ",
                                    "values": [{"userEnteredValue": "USD"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 0.7, "green": 0.9, "blue": 0.7},
                                    "textFormat": {"foregroundColor": {"red": 0, "green": 0, "blue": 0}}
                                }
                            }
                        }
                    }
                },
                # Format RUB in currency column
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 8, "endColumnIndex": 9}],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_EQ",
                                    "values": [{"userEnteredValue": "RUB"}]
                                },
                                "format": {"backgroundColor": {"red": 0.0, "green": 0.0, "blue": 0.9}}
                            }
                        }
                    }
                },
                # Format RUR in currency column (for older data)
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 8, "endColumnIndex": 9}],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_EQ",
                                    "values": [{"userEnteredValue": "RUR"}]
                                },
                                "format": {"backgroundColor": {"red": 0.0, "green": 0.0, "blue": 0.9}}
                            }
                        }
                    }
                },

                # Location formatting rules
                # Format Москва (тёмный с оттенком фиолетового)
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 3, "endColumnIndex": 4}],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_CONTAINS",
                                    "values": [{"userEnteredValue": "Москва"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 0.4, "green": 0.2, "blue": 0.6},
                                    "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}}
                                }
                            }
                        }
                    }
                },
                # Format Санкт-Петербург (тёмный с оттенком жёлтого)
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 3, "endColumnIndex": 4}],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_CONTAINS",
                                    "values": [{"userEnteredValue": "Санкт-Петербург"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 0.6, "green": 0.5, "blue": 0.1},
                                    "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}}
                                }
                            }
                        }
                    }
                },
                # Format США (тёмный с оттенком зелёного)
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 3, "endColumnIndex": 4}],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_CONTAINS",
                                    "values": [{"userEnteredValue": "США"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 0.2, "green": 0.5, "blue": 0.2},
                                    "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}}
                                }
                            }
                        }
                    }
                },
                # Format Барнаул (яркий с оттенком жёлтого и зелёного)
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 3, "endColumnIndex": 4}],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_CONTAINS",
                                    "values": [{"userEnteredValue": "Барнаул"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 0.8, "green": 0.9, "blue": 0.3},
                                    "textFormat": {"foregroundColor": {"red": 0, "green": 0, "blue": 0}}
                                }
                            }
                        }
                    }
                },
                # Format Алматы (тёмный с оттенком синего)
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 3, "endColumnIndex": 4}],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_CONTAINS",
                                    "values": [{"userEnteredValue": "Алматы"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 0.1, "green": 0.3, "blue": 0.7},
                                    "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}}
                                }
                            }
                        }
                    }
                },
                # Format Армения (тёмный с оттенком красного)
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 3, "endColumnIndex": 4}],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_CONTAINS",
                                    "values": [{"userEnteredValue": "Армения"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 0.6, "green": 0.1, "blue": 0.1},
                                    "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}}
                                }
                            }
                        }
                    }
                },
                # Format Минск (тёмный с оттенком зелёного и синего)
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 3, "endColumnIndex": 4}],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_CONTAINS",
                                    "values": [{"userEnteredValue": "Минск"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 0.1, "green": 0.4, "blue": 0.5},
                                    "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}}
                                }
                            }
                        }
                    }
                },
                # Format Екатеринбург (тёмный с оттенком фиолетового и синего)
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 3, "endColumnIndex": 4}],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_CONTAINS",
                                    "values": [{"userEnteredValue": "Екатеринбург"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 0.3, "green": 0.1, "blue": 0.5},
                                    "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}}
                                }
                            }
                        }
                    }
                },
                # Format Белгород (тёмный с оттенком красного и зелёного)
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 3, "endColumnIndex": 4}],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_CONTAINS",
                                    "values": [{"userEnteredValue": "Белгород"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 0.5, "green": 0.3, "blue": 0.1},
                                    "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}}
                                }
                            }
                        }
                    }
                },
                # Format Тбилиси (тёмный с оттенком жёлтого и красного)
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 3, "endColumnIndex": 4}],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_CONTAINS",
                                    "values": [{"userEnteredValue": "Тбилиси"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 0.7, "green": 0.4, "blue": 0.1},
                                    "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}}
                                }
                            }
                        }
                    }
                },
                # Format Сербия (тёмный с оттенком синего и жёлтого)
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 3, "endColumnIndex": 4}],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_CONTAINS",
                                    "values": [{"userEnteredValue": "Сербия"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 0.2, "green": 0.3, "blue": 0.6},
                                    "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}}
                                }
                            }
                        }
                    }
                },
                # Format Астана (тёмный с оттенком розового)
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 3, "endColumnIndex": 4}],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_CONTAINS",
                                    "values": [{"userEnteredValue": "Астана"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 0.6, "green": 0.2, "blue": 0.4},
                                    "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}}
                                }
                            }
                        }
                    }
                },
                # Format Всеволожск (тёмный с оттенком жёлтого и розового)
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 3, "endColumnIndex": 4}],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_CONTAINS",
                                    "values": [{"userEnteredValue": "Всеволожск"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 0.7, "green": 0.5, "blue": 0.4},
                                    "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}}
                                }
                            }
                        }
                    }
                },

                # Format Title Length > 30 (тёмный с оттенком фиолетового)
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 1, "endColumnIndex": 2}],
                            "booleanRule": {
                                "condition": {
                                    "type": "CUSTOM_FORMULA",
                                    "values": [{"userEnteredValue": "=LEN(B)>30"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 0.4, "green": 0.2, "blue": 0.6},
                                    "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}}
                                }
                            }
                        }
                    }
                },
                # Format Title Length < 30 (тёмный с оттенком жёлтого)
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 1, "endColumnIndex": 2}],
                            "booleanRule": {
                                "condition": {
                                    "type": "CUSTOM_FORMULA",
                                    "values": [{"userEnteredValue": "=AND(LEN(B)<=30,LEN(B)>=5)"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 0.6, "green": 0.5, "blue": 0.1},
                                    "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}}
                                }
                            }
                        }
                    }
                },
                # Format Title Length < 5 (тёмный с оттенком зелёного)
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startColumnIndex": 1, "endColumnIndex": 2}],
                            "booleanRule": {
                                "condition": {
                                    "type": "CUSTOM_FORMULA",
                                    "values": [{"userEnteredValue": "=LEN(B)<5"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 0.2, "green": 0.5, "blue": 0.2},
                                    "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}}
                                }
                            }
                        }
                    }
                }
            ]

            try:
                # First try to delete any existing rules
                self.service.spreadsheets().batchUpdate(
                    spreadsheetId=self.sheet_id,
                    body={
                        "requests": [{
                            "deleteConditionalFormatRule": {
                                "sheetId": sheet_id,
                                "index": 0
                            }
                        }]
                    }
                ).execute()
            except Exception as delete_error:
                # If there are no rules to delete, just log and continue
                logger.log_job_processing(
                    "conditional_formatting",
                    "info",
                    {"message": "No existing rules to delete"}
                )

            # Apply new formatting rules
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.sheet_id,
                body={"requests": requests}
            ).execute()

            logger.log_job_processing(
                "conditional_formatting",
                "success",
                {"rules_applied": len(requests)}
            )

        except Exception as e:
            logger.log_error(
                "conditional_formatting_error",
                str(e),
                {}
            )
            raise