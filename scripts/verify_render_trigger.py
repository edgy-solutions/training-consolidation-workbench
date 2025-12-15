import requests
import json

def main():
    url = "http://localhost:8000/render/trigger"
    payload = {
        "project_id": "3355b422-4afe-4d35-8320-48699d7bfd0f",
        "template_name": "master_engineering",
        "format": "pptx"
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print("Render triggered successfully!")
        print(json.dumps(response.json(), indent=2))
    except Exception as e:
        print(f"Error triggering render: {e}")
        if hasattr(e, 'response') and e.response:
             print(e.response.text)

if __name__ == "__main__":
    main()
