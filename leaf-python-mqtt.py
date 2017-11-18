#!/usr/bin/python

import pycarwings2
import time
from ConfigParser import SafeConfigParser
import logging
import sys
import pprint
import paho.mqtt.client as mqtt
import schedule
from datetime import datetime
import os
import json
import pytz

config_file = 'config.ini'


logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logging.info("Startup leaf-python-MQTT: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
config_file_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), config_file)

# Get login details from 'config.ini'
parser = SafeConfigParser()
if os.path.exists(config_file_path):
  logging.info("Loaded config file " + config_file_path)
  #candidates = [ 'config.ini', 'my_config.ini' ]
  candidates = config_file_path
  found = parser.read(candidates)
  username = parser.get('get-leaf-info', 'username')
  password = parser.get('get-leaf-info', 'password')
  mqtt_host = parser.get('get-leaf-info', 'mqtt_host')
  mqtt_port = parser.get('get-leaf-info', 'mqtt_port')
  mqtt_username = parser.get('get-leaf-info', 'mqtt_username')
  mqtt_password = parser.get('get-leaf-info', 'mqtt_password')
  mqtt_control_topic = parser.get('get-leaf-info', 'mqtt_control_topic')
  mqtt_status_topic =  parser.get('get-leaf-info', 'mqtt_status_topic')
  nissan_region_code = parser.get('get-leaf-info', 'nissan_region_code')
  VEHICLE_UPDATE_INTERVAL = parser.get('get-leaf-info', 'vehicle_update_interval_min')
  VEHICLE_STATUS_UPDATE_INTERVAL = parser.get('get-leaf-info', 'status_update_interval_min')
  LOCATION_UPDATE_INTERVAL = parser.get('get-leaf-info', 'location_update_interval_min')
  LOCATION_STATUS_UPDATE_INTERVAL = parser.get('get-leaf-info', 'location_status_update_interval_min')
  local_time_zone = parser.get('get-leaf-info', 'local_time_zone')
  
  if parser.get('get-leaf-info', 'adjust_time_bool') == '0':
      adjust_time_bool = False
  elif parser.get('get-leaf-info', 'adjust_time_bool') == '1':
      adjust_time_bool = True
  else:
      logging.error("Incorrect input for time zone adjustment, please correct config file.")
      exit()
      
  #logging.info("updating data from API every " + GET_UPDATE_INTERVAL +"min")
else:
  logging.error("ERROR: Config file not found " + config_file_path)
  quit()


# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
  logging.info("Connected to MQTT host " + mqtt_host + " with result code "+str(rc))
  logging.info("Suscribing to leaf control topic: " + mqtt_control_topic)
  client.subscribe(mqtt_control_topic + "/#")
  logging.info("Publishing to leaf status topic: " + mqtt_status_topic)
  client.publish(mqtt_status_topic, "MQTT connected");

# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):

    logging.info(msg.topic+" "+str(msg.payload))

    control_subtopic = msg.topic.rsplit('/',1)[1]
    control_message = msg.payload
    logging.info("control sub-topic: " + control_subtopic)
    logging.info("control message: " + control_message)

    # If climate control messaage is received mqtt_control_topic/climate
    if control_subtopic == 'climate':
      logging.info('Climate control command received: ' + control_message)
      try:
        climate_control(int(control_message))
      except ValueError:
        logging.error("Invalid Climate Control Commane Received:  0=Stop, 1=Start, 2=Check Schedule")

    # If climate control messaage is received on mqtt_control_topic/update
    elif control_subtopic == 'update':
      logging.info('Update control command received: ' + control_message)

      if control_message == '1':
        get_leaf_update()
      if control_message == '2':
        get_leaf_status()
      
    
    elif control_subtopic == 'location':
      logging.info('location request: ' + control_message)
      if control_message == '2':
        get_lat_long()
      if control_message == '1':
        update_lat_long()



client = mqtt.Client()
# Callback when MQTT is connected
client.on_connect = on_connect
# Callback when MQTT message is received
client.on_message = on_message
# Connect to MQTT
client.username_pw_set(mqtt_username, mqtt_password);
client.connect(mqtt_host, mqtt_port, 60)
client.publish(mqtt_status_topic, "Connecting to MQTT host " + mqtt_host);
# Non-blocking MQTT subscription loop
client.loop_start()

def login():
  logging.debug("login = %s , password = %s" % ( username , password) )
  logging.info("Prepare Session")
  s = pycarwings2.Session(username, password , nissan_region_code)
  logging.info("Login...")
  logging.info("Start update time: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

  try:
    l = s.get_leaf()
    return l
  except:
    logging.error("CarWings API error")
    return None

def update_lat_long():
  l = login()
  if l == None:
    return None
    
  logging.info("Updating lat/long")
  result_key = l.request_vehicle_lat_long_update()
  print ("Lat Long Result Key: ", result_key)
  update_location_result = l.get_status_from_lat_long_update(result_key)
  logging.info(update_location_result)

def get_lat_long():
  
  l = login()
  if l == None:
    return None
  
  logging.info("Checking lat/long")
  result_key = l.get_vehicle_lat_long()
  logging.info("Lat: %s" % result_key.lat)
  logging.info("Long: %s" % result_key.long)
  time.sleep(10)
  mqtt_publish(result_key, "location")
        
  return result_key


def climate_control(climate_control_instruction):
  l = login()
  if l == None:
    return

  #TODO - use the result as this hasn't been worked out yet
  if climate_control_instruction == 2:
    logging.info("Checking Climate Control Schedule")
    result_key = l.get_climate_control_schedule()
    logging.info(result_key)

  elif climate_control_instruction == 1:
    logging.info("Turning on climate control..wait 60s")
    result_key = l.start_climate_control()
    time.sleep(60)
    start_cc_result = l.get_start_climate_control_result(result_key)
    logging.info(start_cc_result)

  elif climate_control_instruction == 0:
    logging.info("Turning off climate control..wait 60s")
    result_key = l.stop_climate_control()
    time.sleep(60)
    stop_cc_result = l.get_stop_climate_control_result(result_key)
    logging.info(stop_cc_result)

  else:
    logging.info("Invalid Climate Control Key. 0=Stop, 1=Start, 2=Check Schedule")

# Request update from car, use carefully: requires car GSM modem to powerup
def get_leaf_update():
  l = login()
  if l == None:
    return None
  
  logging.info("Requesting update from car..wait 60s")
  try:
    result_key = l.request_update()
  except:
    logging.error("ERROR: no response from car update")
  time.sleep(60)
  battery_status = l.get_status_from_update(result_key)

  while battery_status is None:
    logging.error("ERROR: no responce from car, trying again in 10 seconds")
    time.sleep(10)
    battery_status = l.get_status_from_update(result_key)

  get_leaf_status(l)

  

# Get last updated data from Nissan server
def get_leaf_status(l=None):
  #if not logged in then login
  if l == None:
    l = login()
  #Check if Login Successful, if not return None
  if l == None:
    return None
    
  logging.info("get_latest_battery_status")

  leaf_info = l.get_latest_battery_status()

  if leaf_info:
      logging.info("date %s" % leaf_info.answer["BatteryStatusRecords"]["OperationDateAndTime"])
      logging.info("date %s" % leaf_info.answer["BatteryStatusRecords"]["NotificationDateAndTime"])
      logging.info("battery_capacity2 %s" % leaf_info.answer["BatteryStatusRecords"]["BatteryStatus"]["BatteryCapacity"])
      logging.info("battery_capacity %s" % leaf_info.battery_capacity)
      logging.info("charging_status %s" % leaf_info.charging_status)
      logging.info("battery_capacity %s" % leaf_info.battery_capacity)
      logging.info("battery_remaining_amount %s" % leaf_info.battery_remaining_amount)
      logging.info("charging_status %s" % leaf_info.charging_status)
      logging.info("is_charging %s" % leaf_info.is_charging)
      logging.info("is_quick_charging %s" % leaf_info.is_quick_charging)
      logging.info("plugin_state %s" % leaf_info.plugin_state)
      logging.info("is_connected %s" % leaf_info.is_connected)
      logging.info("is_connected_to_quick_charger %s" % leaf_info.is_connected_to_quick_charger)
      logging.info("time_to_full_trickle %s" % leaf_info.time_to_full_trickle)
      logging.info("time_to_full_l2 %s" % leaf_info.time_to_full_l2)
      logging.info("time_to_full_l2_6kw %s" % leaf_info.time_to_full_l2_6kw)
      logging.info("leaf_info.battery_percent %s" % leaf_info.battery_percent)

      # logging.info("getting climate update")
      # climate = l.get_latest_hvac_status()
      # pprint.pprint(climate)

      mqtt_publish(leaf_info)

      logging.info("End update time: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
      logging.info("Schedule API update every " + GET_UPDATE_INTERVAL + "min")
      return (leaf_info)
  else:
      logging.info("Did not get any response from the API")
      return


def mqtt_publish(leaf_info, info_type="battery"):
  logging.info("End update time: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
  logging.info("publishing to MQTT base status topic: " + mqtt_status_topic)
  
  if info_type == "battery":
    
    #adjust the time from UTC to local Time Zone before sending
    time_to_publish = ""
    if adjust_time_bool:
      time_to_publish = adjustTime(leaf_info.answer["BatteryStatusRecords"]["NotificationDateAndTime"])
    else:
      time_to_publish = leaf_info.answer["BatteryStatusRecords"]["NotificationDateAndTime"]
    
    client.publish(mqtt_status_topic + "/last_updated", time_to_publish)
    
    time.sleep(1)
    client.publish(mqtt_status_topic + "/battery_percent", leaf_info.battery_percent)
    time.sleep(1)
    client.publish(mqtt_status_topic + "/charging_status", leaf_info.charging_status)
    time.sleep(1)
    client.publish(mqtt_status_topic + "/raw", json.dumps(leaf_info.answer))
    time.sleep(1)
    
    if leaf_info.is_connected == True:
      client.publish(mqtt_status_topic + "/connected", "Yes")
    elif leaf_info.is_connected == False:
      client.publish(mqtt_status_topic + "/connected", "No")
    else:
      client.publish(mqtt_status_topic + "/connected", leaf_info.is_connected)
      
  elif info_type == "location":
    client.publish(mqtt_status_topic + "/location_lat", leaf_info.lat)
    time.sleep(1)
    client.publish(mqtt_status_topic + "/location_long", leaf_info.long)
    time.sleep(1)
    
    #adjust the time from UTC to local Time Zone before sending
    time_to_publish = ""
    if adjust_time_bool:
      time_to_publish = adjustTime(leaf_info.receivedDate)
    else:
      time_to_publish = leaf_info.receivedDate
      
    client.publish(mqtt_status_topic + "/location_last_updated", time_to_publish)


def adjustTime(timeToAdjust_UTC, NewTimeZone):
  try:
    localFormat = "%Y/%m/%d %H:%M"
    utcmoment_naive = datetime.strptime(timeToAdjust_UTC, localFormat)
    utcmoment = utcmoment_naive.replace(tzinfo=pytz.utc)
    updatedTimeZone = pytz.timezone(NewTimeZone)
    updatedDatetime = utcmoment.astimezone(updatedTimeZone)
    
    return updatedDatetime
    
        
  except pytz.exceptions.NonExistentTimeError as e:
    logging.error("NonExistentTimeError")
    return timeToAdjust_UTC
#########################################################################################################################
# Run on first time
#get_leaf_status()

# Then schedule
try:
  if int(VEHICLE_UPDATE_INTERVAL) > 0:
    logging.info("Schedule Battery Satus Update (From Vehicle and Server) every " + VEHICLE_UPDATE_INTERVAL + "min")
    schedule.every(int(VEHICLE_UPDATE_INTERVAL)).minutes.do(get_leaf_update)
    
  if int(VEHICLE_STATUS_UPDATE_INTERVAL) > 0:
    logging.info("Schedule Battery Satus Update (From Server Only) every " + VEHICLE_STATUS_UPDATE_INTERVAL + "min")
    schedule.every(int(VEHICLE_STATUS_UPDATE_INTERVAL)).minutes.do(get_leaf_status)
    
  if int(LOCATION_UPDATE_INTERVAL) > 0:
    logging.info("Schedule Location update (From Vehicle and Server) every " + LOCATION_UPDATE_INTERVAL + "min")
    schedule.every(int(LOCATION_UPDATE_INTERVAL)).minutes.do(update_lat_long)
    
  if int(LOCATION_STATUS_UPDATE_INTERVAL) > 0:
    logging.info("Schedule Location update (From Server Only) every " + LOCATION_STATUS_UPDATE_INTERVAL + "min")
    schedule.every(int(LOCATION_STATUS_UPDATE_INTERVAL)).minutes.do(get_lat_long)
except ValueError:
  logging.error("Incorrect Value in update interval from configuration. Please check configuration and retry.")
  exit()


while True:
    schedule.run_pending()
    time.sleep(1)
