from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.chrome.service import Service
import time
from datetime import datetime, timedelta
from selenium.webdriver.chrome.options import Options
import os
from tempfile import mkdtemp
from dotenv import load_dotenv
import json
import asyncio
from telegram import Bot
import logging
import signal
import sys

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('appointment_checker.log'),
            logging.StreamHandler()  # This will also print to console
        ]
    )
    return logging.getLogger(__name__)

class AppointmentChecker:
    def __init__(self, run, password, telegram_token=None, telegram_chat_id=None):
        self.run = run
        self.password = password
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self.state_file = 'appointment_state.json'
        
        # Setup Chrome options
        chrome_options = Options()
        chrome_options.binary_location = "/snap/bin/chromium"
        
        # Create a temporary directory for user data
        user_data_dir = mkdtemp()
        chrome_options.add_argument(f'--user-data-dir={user_data_dir}')
        
        # Headless mode settings
        chrome_options.add_argument('--headless=new')  # New headless mode
        chrome_options.add_argument('--window-size=1920,1080')  # Set a standard window size
        chrome_options.add_argument('--start-maximized')
        
        # Additional stability options
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-setuid-sandbox')
        chrome_options.add_argument('--disable-web-security')
        chrome_options.add_argument('--dns-prefetch-disable')
        chrome_options.add_argument('--disable-features=VizDisplayCompositor')
        chrome_options.add_argument('--remote-debugging-port=9222')
        
        # Add additional headers
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
        
        # Setup ChromeDriver service with local path
        service = Service('./chromedriver')
        
        self.driver = webdriver.Chrome(
            service=service,
            options=chrome_options
        )
        self.wait = WebDriverWait(self.driver, 10)
        self.user_data_dir = user_data_dir  # Store for cleanup
        self.logger = logging.getLogger(__name__)

    def login(self):
        # Navigate to the website
        self.driver.get("https://solicitudeswebrc.srcei.cl/ReservaDeHoraSRCEI/web/init.srcei")
        
        # Wait for page to be fully loaded
        self.wait.until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(2)  # Additional wait for dynamic content
        
        # Find and fill the username (RUN) field
        username_field = self.wait.until(
            EC.presence_of_element_located((By.ID, "cu_inputRUN"))
        )
        username_field.send_keys(self.run)

        # Find and fill the password field
        password_field = self.wait.until(
            EC.presence_of_element_located((By.ID, "cu_inputClaveUnica"))
        )
        password_field.send_keys(self.password)

        # Click the authenticate button with correct ID
        auth_button = self.wait.until(
            EC.element_to_be_clickable((By.ID, "cu_btnIngresar"))
        )
        auth_button.click()

    def navigate_to_reimpresion(self):
        try:
            # First try by ID and text content
            reimpresion_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[@id='9' and contains(text(), 'Reimpresión cédula')]"))
            )
        except:
            try:
                # Try by class and text content
                reimpresion_button = self.wait.until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//button[@class='btn btn-light listaModulos' and contains(text(), 'Reimpresión cédula')]")
                    )
                )
            except:
                # Last resort - try just by ID
                reimpresion_button = self.wait.until(
                    EC.element_to_be_clickable((By.ID, "9"))
                )
        
        reimpresion_button.click()

    async def send_telegram_message(self, message):
        if self.telegram_token and self.telegram_chat_id:
            bot = Bot(self.telegram_token)
            await bot.send_message(chat_id=self.telegram_chat_id, text=message)

    def load_previous_state(self):
        try:
            with open(self.state_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def save_state(self, state):
        with open(self.state_file, 'w') as f:
            json.dump(state, f)

    def parse_appointment_date(self, appointment_str):
        # Parse "07 Abril 08:46" into datetime
        day, month, time = appointment_str.split()
        month_map = {
            'Enero': 1, 'Febrero': 2, 'Marzo': 3, 'Abril': 4,
            'Mayo': 5, 'Junio': 6, 'Julio': 7, 'Agosto': 8,
            'Septiembre': 9, 'Octubre': 10, 'Noviembre': 11, 'Diciembre': 12
        }
        month_num = month_map[month]
        hour, minute = map(int, time.split(':'))
        year = datetime.now().year
        return datetime(year, month_num, int(day), hour, minute)

    def check_appointment(self, region_id, offices, days_to_search=30):
        self.logger.info(f"Starting appointment check for region {region_id}")
        
        # Load previous state at the start
        previous_state = self.load_previous_state()
        previous_earliest = None
        cutoff_date = None  # Will be set if current appointment is still valid
        
        # First check if previous earliest appointment is still available
        if 'earliest' in previous_state:
            previous_appointment = previous_state['earliest']
            previous_earliest = self.parse_appointment_date(previous_appointment['appointment'])
            previous_office = previous_appointment['office']
            
            self.logger.info(f"Checking if previous appointment is still available: {previous_appointment['appointment']} at {previous_office}")
            
            # Select region from dropdown
            region_dropdown = Select(self.wait.until(
                EC.presence_of_element_located((By.ID, "selectRegion"))
            ))
            region_dropdown.select_by_value(region_id)
            time.sleep(2)
            
            # Get office dropdown and select previous office
            office_dropdown = Select(self.wait.until(
                EC.presence_of_element_located((By.ID, "selectOficinas"))
            ))
            
            try:
                office_dropdown.select_by_visible_text(previous_office)
                
                # Parse the date from the previous appointment using our existing parse_appointment_date method
                prev_date = self.parse_appointment_date(previous_appointment['appointment'])
                formatted_date = prev_date.strftime("%d/%m/%Y")
                
                # Check that specific date
                date_field = self.wait.until(
                    EC.presence_of_element_located((By.ID, "idFechaSeleccionadaDesde"))
                )
                self.driver.execute_script("arguments[0].removeAttribute('readonly')", date_field)
                date_field.clear()
                date_field.send_keys(formatted_date)
                
                # Click search button
                search_button = self.wait.until(
                    EC.element_to_be_clickable((By.ID, "idBtnBuscarFechaDisponible"))
                )
                search_button.click()
                
                # Wait for loader
                self.wait.until(
                    EC.presence_of_element_located((By.ID, "idBuscarHoraLoaderContainer"))
                )
                self.wait.until(
                    EC.invisibility_of_element_located((By.ID, "idBuscarHoraLoaderContainer"))
                )
                
                # Check if the appointment is still there
                appointments_container = self.wait.until(
                    EC.presence_of_element_located((By.ID, "idHorasDisponiblesContainer"))
                )
                appointment_cards = appointments_container.find_elements(
                    By.XPATH, ".//div[contains(@class, 'card') and not(contains(@style, 'display: none'))]"
                )
                
                appointment_still_available = False
                for card in appointment_cards:
                    try:
                        day = card.find_element(By.TAG_NAME, "h1").text
                        month = card.find_element(By.TAG_NAME, "h5").text
                        appointment_time = card.find_element(By.TAG_NAME, "h6").text
                        if f"{day} {month} {appointment_time}" == previous_appointment['appointment']:
                            appointment_still_available = True
                            break
                    except:
                        continue
                
                if appointment_still_available:
                    self.logger.info("Previous appointment is still available")
                    # Set cutoff date to the current appointment date
                    cutoff_date = previous_earliest
                    
                else:
                    self.logger.info("Previous appointment is no longer available!")
                    notification = (
                        f"Previous appointment is no longer available!\n"
                        f"Lost appointment: {previous_appointment['appointment']} at {previous_office}\n"
                        f"Searching for new earlier appointment..."
                    )
                    asyncio.run(self.send_telegram_message(notification))
                    previous_earliest = None  # Reset so we'll treat next found appointment as first
                    self.save_state({})  # Clear the previous state
            
            except Exception as e:
                self.logger.error(f"Error checking previous appointment: {str(e)}")
                # Continue with regular search even if checking previous appointment fails
        
        # Continue with regular appointment search
        # Select region again to ensure clean state
        region_dropdown = Select(self.wait.until(
            EC.presence_of_element_located((By.ID, "selectRegion"))
        ))
        region_dropdown.select_by_value(region_id)
        time.sleep(2)
        
        # Get office dropdown
        office_dropdown = Select(self.wait.until(
            EC.presence_of_element_located((By.ID, "selectOficinas"))
        ))
        
        available_appointments = {}
        earliest_appointment = None
        earliest_office = None
        
        # Check each office
        for office in offices:
            try:
                self.logger.info(f"Checking office: {office}")
                office_dropdown.select_by_visible_text(office)
                office_appointments = []
                
                # Check next X days, but only up to cutoff_date if it exists
                current_date = datetime.now()
                for i in range(days_to_search):
                    check_date = current_date + timedelta(days=i)
                    
                    # Skip dates after the cutoff date if it exists
                    if cutoff_date and check_date.date() > cutoff_date.date():
                        self.logger.info(f"Skipping remaining dates for {office} as they are after current appointment")
                        break
                    
                    formatted_date = check_date.strftime("%d/%m/%Y")
                    
                    try:
                        # Find and update date field
                        date_field = self.wait.until(
                            EC.presence_of_element_located((By.ID, "idFechaSeleccionadaDesde"))
                        )
                        self.driver.execute_script("arguments[0].removeAttribute('readonly')", date_field)
                        date_field.clear()
                        date_field.send_keys(formatted_date)
                        
                        # Click search button
                        search_button = self.wait.until(
                            EC.element_to_be_clickable((By.ID, "idBtnBuscarFechaDisponible"))
                        )
                        search_button.click()

                        # Wait for loader to appear and disappear
                        self.wait.until(
                            EC.presence_of_element_located((By.ID, "idBuscarHoraLoaderContainer"))
                        )
                        self.wait.until(
                            EC.invisibility_of_element_located((By.ID, "idBuscarHoraLoaderContainer"))
                        )

                        # Check for available appointments more efficiently
                        appointments_container = self.wait.until(
                            EC.presence_of_element_located((By.ID, "idHorasDisponiblesContainer"))
                        )

                        # Get all card data at once using a single JavaScript execution
                        cards_data = self.driver.execute_script("""
                            const cards = document.querySelectorAll('#idHorasDisponiblesContainer .card:not([style*="display: none"])');
                            return Array.from(cards).map(card => ({
                                day: card.querySelector('h1').textContent,
                                month: card.querySelector('h5').textContent,
                                time: card.querySelector('h6').textContent
                            }));
                        """)

                        for card_data in cards_data:
                            try:
                                appointment_str = f"{card_data['day']} {card_data['month']} {card_data['time']}"
                                
                                # Check if this appointment is earlier than our previous earliest
                                current_date = self.parse_appointment_date(appointment_str)
                                if previous_earliest and current_date < previous_earliest:
                                    notification = (
                                        f"New earlier appointment found!\n"
                                        f"Previous: {previous_state['earliest']['appointment']} at {previous_state['earliest']['office']}\n"
                                        f"New: {appointment_str} at {office}"
                                    )
                                    self.logger.info(f"New earlier appointment found: {appointment_str} at {office}")
                                    asyncio.run(self.send_telegram_message(notification))
                                    
                                    # Update state immediately
                                    self.save_state({
                                        'earliest': {
                                            'appointment': appointment_str,
                                            'office': office
                                        }
                                    })
                                    # Update previous_earliest for subsequent comparisons
                                    previous_earliest = current_date
                                elif not previous_earliest:  # First appointment ever found
                                    notification = (
                                        f"First appointment found!\n"
                                        f"Date: {appointment_str} at {office}"
                                    )
                                    self.logger.info("First appointment found")
                                    asyncio.run(self.send_telegram_message(notification))
                                    
                                    # Save initial state
                                    self.save_state({
                                        'earliest': {
                                            'appointment': appointment_str,
                                            'office': office
                                        }
                                    })
                                    previous_earliest = current_date
                                    
                                office_appointments.append(appointment_str)
                            except Exception as e:
                                self.logger.error(f"Error processing appointment data: {str(e)}")
                                continue
                
                    except Exception as e:
                        error_msg = f"Error checking date {formatted_date} for office {office}: {str(e)}"
                        self.logger.error(error_msg)
                        print(error_msg)
                        continue

                if office_appointments:
                    self.logger.info(f"Found {len(office_appointments)} appointments for {office}")
                    # Sort appointments by date
                    sorted_appointments = sorted(
                        office_appointments,
                        key=lambda x: self.parse_appointment_date(x)
                    )
                    available_appointments[office] = sorted_appointments
                    
                    if earliest_appointment is None or self.parse_appointment_date(sorted_appointments[0]) < self.parse_appointment_date(earliest_appointment):
                        earliest_appointment = sorted_appointments[0]
                        earliest_office = office

                print(f"Checked {office} for next {days_to_search} days")

            except Exception as e:
                error_msg = f"Error checking office {office}: {str(e)}"
                self.logger.error(error_msg)
                print(error_msg)
                continue

        return available_appointments

    def close(self):
        self.driver.quit()
        # Clean up the temporary directory
        try:
            import shutil
            shutil.rmtree(self.user_data_dir)
        except:
            pass

def signal_handler(signum, frame):
    logger = logging.getLogger(__name__)
    logger.info("Received shutdown signal, exiting gracefully")
    print("\nShutting down gracefully...")
    sys.exit(0)

def main():
    # Setup signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Setup logging
    logger = setup_logging()
    logger.info("Starting appointment checker")
    
    # Load environment variables
    load_dotenv()
    
    # Get credentials from environment variables
    run = os.getenv('RUN')
    password = os.getenv('PASSWORD')
    region_id = os.getenv('REGION')
    offices = os.getenv('OFFICES').split(',')
    telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
    telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
    days_to_search = int(os.getenv('DAYS_TO_SEARCH', '30'))
    wait_time = int(os.getenv('WAIT_TIME', '60'))  # Default to 60 seconds if not set
    
    if not all([run, password, region_id, offices]):
        logger.error("Missing required environment variables")
        print("Error: RUN, PASSWORD, REGION, and OFFICES must be set in .env file")
        return

    while True:
        checker = None
        try:
            checker = AppointmentChecker(
                run, 
                password,
                telegram_token=telegram_token,
                telegram_chat_id=telegram_chat_id
            )
            
            logger.info("Attempting login")
            checker.login()
            logger.info("Login successful")
            
            checker.navigate_to_reimpresion()
            logger.info("Navigated to reimpresion page")

            logger.info(f"Checking availability for region {region_id} for the next {days_to_search} days")
            available_appointments = checker.check_appointment(region_id, offices, days_to_search)
            
            if available_appointments:
                logger.info("Available appointments found")
                for office, appointments in available_appointments.items():
                    logger.info(f"{office}: {len(appointments)} appointments")
            else:
                logger.info("No available appointments found")

        except Exception as e:
            error_msg = f"An error occurred: {str(e)}"
            logger.error(error_msg)
            print(error_msg)
            if checker:
                asyncio.run(checker.send_telegram_message(f"Error en el checker: {str(e)}"))
        finally:
            if checker:
                logger.info("Closing current checker instance")
                checker.close()
            
            # Wait before starting the next run
            logger.info(f"Waiting {wait_time} seconds before next run")
            time.sleep(wait_time)
            logger.info("Starting new run")

if __name__ == "__main__":
    main() 
