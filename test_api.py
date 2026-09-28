import requests
base="http://127.0.0.1:8000"
print(requests.get(base+"/api/health").json())
demands=requests.get(base+"/api/demands").json()
print("demands:",len(demands))
print(requests.get(base+"/api/predict/"+demands[0]["demand_id"]).json()["model"]["prediction"])
