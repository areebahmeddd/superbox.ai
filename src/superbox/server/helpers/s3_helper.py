import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from superbox.shared.s3 import (
    get_server,
    list_servers,
    upsert_server,
    delete_server,
)

if __name__ == "__main__":
    try:
        input_data = json.loads(sys.argv[1])
        function = input_data["function"]
        args = input_data["args"]

        if function == "get_server":
            result = get_server(args["bucket_name"], args["server_name"])
            output = {"data": result}
        elif function == "list_servers":
            result = list_servers(args["bucket_name"])
            output = {"data": result}
        elif function == "upsert_server":
            result = upsert_server(args["bucket_name"], args["server_name"], args["server_data"])
            output = {"success": result}
        elif function == "delete_server":
            result = delete_server(args["bucket_name"], args["server_name"])
            output = {"success": result}
        else:
            output = {"error": f"Unknown function: {function}"}

        print(json.dumps(output))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
