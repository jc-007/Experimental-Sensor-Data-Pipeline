import numpy as np
import pandas as pd


sensor_readings = []
data_valid = True

#for i in range(100):
    #temp = round(np.random.normal(90, 20),2)
    #pressure = round(np.random.normal(28, 7),2)
    #vol = round(np.random.normal(220, 12),2)
temp = None 
pressure = -5.2
vol = 900

try:
    # Temperature Validation
    if temp > 400 or temp < 20:
        v_error1 = "Incorrect temperature"
        data_valid = False
    else:
        v_error1 =""

    # Temperature risk
    if temp > 140:
        t_risk = 5
    elif temp > 120  and temp <= 140:
        t_risk = 2
    else:
        t_risk = 0

    #Pressure Validation
    if pressure < 0:
        v_error2 = "Negative pressure"
        data_valid = False
    else:
        v_error2=""

    # Pressure risk
    if pressure > 40:
        p_risk = 5
    elif pressure > 35 and pressure <= 40:
        p_risk = 2
    else:
        p_risk = 0

    #Volate Validation
    if vol > 500:
        v_error3 = "Incorrect High Voltage"
        data_valid = False
    else:
        v_error2=""

    # Voltage risk
    if vol > 250 and vol < 190:
        v_risk = 5
    elif vol > 240 and vol < 230:
        v_risk = 2
    else:
        v_risk = 0

    # Overall machine status
    if t_risk == 5 or p_risk == 5 or v_risk == 5:
        status = "BREAKDOWN RISK"
        alert = "HIGH ALERT"

    elif t_risk == 2 or p_risk == 2 or v_risk == 2:
        status = "RUNNING"
        alert = "MODERATE ALERT"

    else:
        status = "RUNNING"
        alert = "NO ALERT"

    risk_score = p_risk + v_risk + t_risk

except TypeError:
    v_error1 = "Incorrect temperature"
    v_error2 = "Negative pressure"
    v_error3 = "Incorrect High Voltage"
    validation_error = v_error1 + ", " + v_error2 + ", " + v_error3

else:
    sensor_data = {
    #    "sensor_id": f"SENSOR-{i+1:04d}",
    #    "equipment_id": f"PUMP-{i+0:04d}",

        "sensor_id": "SENSOR-0101",
        "equipment_id": "PUMP-011",

        "temperature": temp,
        "pressure": pressure,
        "voltage": vol,
        "status": status,
        "alert": alert,
        "risk_score" : risk_score,
        "data_valid": data_valid,
        "validation_error": validation_error
    }
    sensor_readings.append(sensor_data)

    #print(sensor_readings)
df = pd.DataFrame(sensor_readings)

print(df.head())
print(df.shape)
print(df.info())
print(df.describe())

print("Risk Score Mean - ", df["risk_score"].mean())
print("Maximum Equipment Temperature- ",df["temperature"].max())
print("High Alerts :- \n",df[df["alert"] == "HIGH ALERT"])

print(df["alert"].value_counts())

