import os
import pickle
import datetime
import requests
import random
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# Define SCOPES for Google Calendar API
SCOPES = ['https://www.googleapis.com/auth/calendar']

# Google Calendar Authentication
def authenticate_google_calendar():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'client_secret.json', SCOPES)
            creds = flow.run_local_server(port=8080)

        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return creds

# Fetch Google Calendar events and find free time slots
def fetch_schedule_and_free_times(creds):
    try:
        service = build('calendar', 'v3', credentials=creds)
        now = datetime.datetime.now(datetime.timezone.utc)
        time_max = now + datetime.timedelta(days=7)

        events_result = service.events().list(
            calendarId='primary',
            timeMin=now.isoformat(),
            timeMax=time_max.isoformat(),
            maxResults=50,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        free_slots = []
        last_end_time = now

        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))

            start_time = datetime.datetime.fromisoformat(start).astimezone(datetime.timezone.utc)
            end_time = datetime.datetime.fromisoformat(end).astimezone(datetime.timezone.utc)

            time_difference = (start_time - last_end_time).total_seconds() / 3600
            if time_difference >= 1:
                free_slots.append((last_end_time, start_time))

            last_end_time = end_time

        end_date = now + datetime.timedelta(days=7)
        if last_end_time < end_date:
            free_slots.append((last_end_time, end_date))

        readable_free_slots = []
        for start, end in free_slots:
            local_tz = datetime.datetime.now().astimezone().tzinfo
            local_start = start.astimezone(local_tz)
            local_end = end.astimezone(local_tz)
            start_str = local_start.strftime('%m/%d/%Y %I:%M %p')
            end_str = local_end.strftime('%m/%d/%Y %I:%M %p')
            readable_free_slots.append(f"From {start_str} to {end_str}")

        return readable_free_slots, free_slots, events

    except Exception as error:
        print(f'Error fetching schedule: {error}')
        return [], [], []

# Fetch events from Gemini API
def fetch_events_from_gemini(free_times):
    GEMINI_API_KEY = 'YOUR_GEMINI_API_KEY'  # Ensure you securely manage your API key
    gemini_api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

    time_slots = []
    for time_slot in free_times:
        try:
            start_time_str, end_time_str = time_slot.split(" to ")
            start_time = datetime.datetime.strptime(start_time_str.replace("From ", "").strip(), "%m/%d/%Y %I:%M %p")
            end_time = datetime.datetime.strptime(end_time_str.strip(), "%m/%d/%Y %I:%M %p")
            time_slots.append({
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat()
            })
        except ValueError as e:
            print(f"Error processing time slot '{time_slot}': {e}")
            continue

    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": f"Surprise me with an event for someone 18 years old in Los Angeles. It should be during these time slots: {time_slots}. Just pick one event that fits." # Edit prompt for your needs
                    }
                ]
            }
        ]
    }

    headers = {'Content-Type': 'application/json'}
    response = requests.post(gemini_api_url, json=data, headers=headers)

    if response.status_code == 200:
        response_data = response.json()

        if "candidates" in response_data:
            return random.choice(response_data["candidates"])
        else:
            print("No events found in the Gemini response.")
            return None
    else:
        print(f"Error with Gemini API: {response.status_code} - {response.text}")
        return None

# Create event in Google Calendar
def create_event(gemini_event, selected_timeslot):
    creds = authenticate_google_calendar()
    service = build('calendar', 'v3', credentials=creds)

    event_description = gemini_event['content']['parts'][0]['text']
    start_time_str = selected_timeslot['start_time']
    end_time_str = selected_timeslot['end_time']

    start_time = datetime.datetime.fromisoformat(start_time_str)
    end_time = datetime.datetime.fromisoformat(end_time_str)

    event_title = input("\nEnter a title for this event: ")

    event_data = {
        'summary': event_title,
        'location': 'Los Angeles',
        'description': event_description,
        'start': {
            'dateTime': start_time.isoformat(),
            'timeZone': 'America/Los_Angeles',
        },
        'end': {
            'dateTime': end_time.isoformat(),
            'timeZone': 'America/Los_Angeles',
        }
    }

    try:
        event = service.events().insert(calendarId='primary', body=event_data).execute()
        print(f"Event created successfully: {event.get('htmlLink')}")
    except Exception as e:
        print(f"Error creating the event in Google Calendar: {e}")

# Main function to run the workflow
def main():
    creds = authenticate_google_calendar()
    free_times, free_slots, _ = fetch_schedule_and_free_times(creds)

    if not free_times:
        print("No free time slots found in your calendar.")
        return

    print("\nAvailable time slots:")
    for i, slot in enumerate(free_times, 1):
        print(f"{i}. {slot}")

    try:
        choice = int(input(f"\nChoose a slot (1-{len(free_times)}): ")) - 1
        if not 0 <= choice < len(free_slots):
            raise ValueError
    except ValueError:
        print("Invalid selection")
        return

    start, end = free_slots[choice]
    location = input("\nEnter location (default: Los Angeles): ") or "Los Angeles"

    print(f"\nSearching events in {location}...")

    gemini_event = fetch_events_from_gemini(free_times)

    if gemini_event:
        print(f"\nSurprise! Here's an event that fits your schedule:")
        print(f"Event: {gemini_event['content']['parts'][0]['text']}")
        print(f"Details: {gemini_event.get('url', 'No URL available')}")

        create_event(gemini_event, {'start_time': start.isoformat(), 'end_time': end.isoformat()})
    else:
        print("\nNo event found. Try adjusting your search parameters.")

if __name__ == "__main__":
    main()
