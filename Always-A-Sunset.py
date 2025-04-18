import streamlit as st
from datetime import time, timezone, date, datetime
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as Service
from webdriver_manager.core.os_manager import ChromeType
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
import csv
import pycountry 

dev = False#Selenium setting. Dev needed to run locally, no dev if we want to run in streamlit cloud.

st.set_page_config(page_title = "Always a sunset")
st.title("Find a sunrise or sunset around the world")
st.caption("Created by Drew Warner with cameras by EarthCam")
st.caption("Version 1.1")

def launch_browser():
    #initialize selenium to get our responses here. This is necessary because the base html returned by requests uses weird obj.-- objects, but this returns proper links and ids.
    options = Options()


    options.add_argument('--headless=new')


    #reduce mem usage, with some options
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-networking")
    options.add_argument("--remote-debugging-port=9222")
    options.add_argument("--disable-logging")
    options.add_argument("--log-level=3")
    #reduce detectability as bot with some more options
    options.add_argument("--disable-blink-features=AutomationControlled")#make it not openly admit to being a bot
    custom_ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "#make us not look exactly like a bot, where this would say HeadlessChrome
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/90.0.4430.212 Safari/537.36")
    options.add_argument(f"user-agent={custom_ua}")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    if not dev:
        browser = webdriver.Chrome(service=Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()), options=options)
    else:
        browser = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    browser.set_window_size(500, 500)
    #a bit more anti-anti-bot
    browser.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": """
        //remove the webdriver property
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        //fake the languages property
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        //fake the plugins property (just need a non-zero length)
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        """})
    return browser

if "cam_details" not in st.session_state:#we only want to do this once, as it is time consuming
    with st.spinner("Finding available camera locations..."):
        with st.spinner("Finding countries and states..."):
            resp = requests.get("https://earthcam.com/network/")
            soup = BeautifulSoup(resp.text, 'html.parser')
            camera_links = soup.find_all('a', class_='locationLink')
            camera_locations = [link.get('href') for link in camera_links]
            full_links = []
            loc_names = []
            for link in camera_locations:
                if "Russia" not in camera_locations and link != "index.php?page=world&country=":#russia is a special link that has many links contained within. We don't like it. 
                    #We also don't like the one that is just a null pointer to a non-existent country. It is probably caused by the separation between US and world locations.
                    if "country=us&" not in link:#this is a world location
                        loc_names.append("".join(link[link.find("country=")+8:]))
                        full_links.append("https://earthcam.com/network/?"+"".join(link[link.find("country="):]))
                    else:#US location
                        loc_names.append("".join(link[link.find("page=")+5:])+", United States")
                        full_links.append("https://earthcam.com/network/?"+"".join(link[link.find("page="):])+"&"+"".join(link[link.find("country="):link.find("&page=")]))
        with st.spinner("Finding each camera..."):
            with st.spinner("Loading finder..."):
                browser = launch_browser()
        #now, for each of these links, find each available camera location.
        every_location_name = []
        every_location_link = []
        prog_bar = st.progress(0, text="Locations searched: 0/"+str(len(full_links)))
        failed = False#if the selenium timed out, don't cause a failure down the line
        for i in range(len(full_links)):
            prog_bar.progress(i/len(full_links), text="Locations searched: "+str(i)+"/"+str(len(full_links)))
            try:
                browser.get(full_links[i])#get the page
            except:#selenium crashed, relaunch and try again.
                browser.quit()
                browser = launch_browser()
                i -= 1
                continue
            #wait for page load
            try:
                WebDriverWait(browser, 30).until(
                    EC.presence_of_element_located((By.ID, "featuredCamText")) 
                    # or other locators like By.XPATH, By.CSS_SELECTOR
                )
            except:
                st.error("Request timeout detected. Please try again later")
                failed = True
                break
            #extract html data that we need (town name and link to cam)
            soup = BeautifulSoup(browser.page_source, 'html.parser')
            l_names = soup.find_all("div", class_='featuredCity')
            loc_links = soup.find_all('a', class_='featuredTitleLink')

            #extract html data
            loc_names_processed = [loc_name.get_text() for loc_name in l_names]
            loc_links = [loc_link.get('href') for loc_link in loc_links]

            #add rest of placename to it (city, state, country, or similar)

            l_names_processed = []
            for name in loc_names_processed:
                name = name+", "+loc_names[i]
                l_names_processed.append(name)
            for j in range(min([len(l_names_processed), len(loc_links)])):#Go through each and add it to the final lists. If one is shorter, avoid index errors
                every_location_link.append(loc_links[j])
                every_location_name.append(l_names_processed[j])
        prog_bar.empty()

        #set up the permanent streamlit environment variables
        st.session_state.all_cam_locations = every_location_name#all_cam_locations is the names of each camera location
        st.session_state.all_cam_urls = every_location_link


        
    with st.spinner("Cleaning up..."):
        browser.quit()
    if not failed:
        with st.spinner("Finding physical locations of cameras..."):
            #load the dataset of cities
            cities = {}
            with open("cities500.txt", encoding='utf-8') as f:
                reader = csv.reader(f, delimiter='\t')
                for row in reader:
                    name = row[1].strip().lower()
                    country = row[8].strip().lower()
                    key = f"{name},{country}"
                    lat, lon = float(row[4]), float(row[5])
                    #keep only the first match or most populous version
                    if key not in cities:
                        cities[key] = (lat, lon)

            def country_to_code(country_name):#Turns "France" into "FR", etc
                try:
                    return pycountry.countries.lookup(country_name.strip()).alpha_2
                except LookupError:
                    return None            
            def get_coords(location_str, db):#get coordinates of location, i.e. Paris, France or Tokyo, Japan
                parts = [p.strip() for p in location_str.split(',')]
                if len(parts) < 2:
                    return None#not enough info to find the location

                city = parts[0].lower()
                country_part = parts[-1]
                country_code = country_to_code(country_part)
                if not country_code:
                    return None

                key = f"{city},{country_code.lower()}"
                return db.get(key)

            st.session_state.cam_details = []#this has the details of the camera [longitude, url], as those are neccessary for finding the sunrise/sunset, but not the name or location of the camera
            prog_bar = st.progress(0, text="Locations searched: 0/"+str(len(st.session_state.all_cam_locations)))
            for i in range(len(st.session_state.all_cam_locations)):
                coords = get_coords(st.session_state.all_cam_locations[i], cities)
                if coords:
                    st.session_state.cam_details.append([coords[1], st.session_state.all_cam_urls[i]])
                prog_bar.progress(i/len(st.session_state.all_cam_locations), 
                                text="Locations searched: "+str(i)+"/"+str(len(st.session_state.all_cam_locations)))
            prog_bar.empty()
            st.success("Cameras found: "+str(len(st.session_state.cam_details)))
        with st.spinner("Cleaning up..."):
            del st.session_state.all_cam_locations
            del st.session_state.all_cam_urls


def calc_timediff(time1, time2):
    datetime1 = datetime.combine(date.today(), time1)
    datetime2 = datetime.combine(date.today(), time2)
    delta = datetime1-datetime2
    return delta.total_seconds()/3600#return total hours.

def find_longdist(long1, long2):#this makes sure we calculate for timezones that are technically at nearly opposite longitudes
    dist1 = abs(long1-long2)
    dist2 = abs((long1+360)-long2)
    dist3 = abs((long1-360)-long2)
    return min([dist1, dist2, dist3])

def load_sun_time(sun):#sun 1 = sunrise, 2 = sunset
    if sun == 1:
        times = [time(8, 00), time(7, 15), time(6, 15), time(5, 30),
            time(4, 45), time(4, 30), time(4, 45), time(5, 30), time(6, 15),
            time(7, 00), time(7, 45), time(8, 00)]
    else:
        times = [time(16, 00), time(17, 00), time(18, 00), time(19, 30),
                    time(20, 30), time(21, 00), time(20, 45), time(20, 00),
                    time(19, 00), time(18, 00), time(16, 30), time(16, 00)]
    now = datetime.now(timezone.utc)#current utc time
    st.caption("Utc now: "+str(now))
    month_index = now.month-1#gets current month index, I.E. jan = 0
    sun_time = times[month_index]
    time_zone_longitude=15#how much longitude 1 timezone takes up
    sun_delta = calc_timediff(sun_time, now.time())#how many timezones we need to shift, to the left.

    long_delta = sun_delta*time_zone_longitude#the actual longitude of sunrise right now. Times tested to be reasonably accurate on 4/12/2025

    #make sure that the longitudes are not impossible (they have to be -180<=x<=180)
    if long_delta < -180:
        long_delta += 360
    if long_delta > 180:
        long_delta -= 360
    #search through the list for the closest to this longitude
    goal_long = long_delta

    best_cam = st.session_state.cam_details[0][1]#this is the url
    best_dist = find_longdist(st.session_state.cam_details[0][0], goal_long)#this is the distance

    for i in range(1, len(st.session_state.cam_details)):
        this_camdist = find_longdist(st.session_state.cam_details[i][0], goal_long)
        if this_camdist < best_dist:
            best_dist = this_camdist
            best_cam = st.session_state.cam_details[i][1]
    return best_cam, best_dist


#sunrise and sunset times are UST-0 without any DST or similar applied, expressed on a 24-hour clock
#Each element corresponds to a month, so element 0 is Jan, etc.
if st.button("Load sunrise"):
    with st.spinner("Loading location..."):
        best_cam, best_dist = load_sun_time(1)
    if best_dist*69 < 250:
        st.caption("Approximate distance from cam to sunrise front: "+str(round(best_dist*69))+" miles/"+str(round(best_dist*111))+" kilometers")
        st.link_button("Go to feed", best_cam)
    else:
        st.error("No sunrise feed found")

if st.button("Load sunset"):
    with st.spinner("Loading location..."):
        best_cam, best_dist = load_sun_time(2)
    if best_dist*69 < 250:#make sure we're somewhat close
        st.caption("Approximate distance from cam to sunset front: "+str(round(best_dist*69))+" miles/"+str(round(best_dist*111))+" kilometers")
        st.link_button("Go to feed", best_cam)
    else:
        st.error("No sunset feed found")
if st.button("Load best sunrise or sunset"):
    rise_cam, rise_dist = load_sun_time(1)
    set_cam, set_dist = load_sun_time(2)
    if rise_dist*69 < 250 or set_dist*69 < 250:
        if rise_dist < set_dist:
            st.caption("Approximate distance from cam to sunrise front: "+str(round(rise_dist*69))+" miles/"+str(round(rise_dist*111))+" kilometers")
            st.link_button("Go to feed", rise_cam)
        else:
            st.caption("Approximate distance from cam to sunset front: "+str(round(set_dist*69))+" miles/"+str(round(set_dist*111))+" kilometers")
            st.link_button("Go to feed", set_cam)
    else:
        st.error("No sunset or sunrise feed found")