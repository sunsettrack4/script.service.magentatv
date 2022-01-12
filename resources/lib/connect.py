import os, requests, xbmc, xbmcaddon
from bs4 import BeautifulSoup
from uuid import uuid4


# ADDON INFO
__addon__ = xbmcaddon.Addon()
data_dir = xbmc.translatePath(__addon__.getAddonInfo('profile'))

# DEFAULT HEADER
header = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.3",
    "Content-Type": "application/x-www-form-urlencoded"}


# RETRIEVE HIDDEN XSRF + TID VALUES TO BE TRANSMITTED TO ACCOUNTS PAGE
def parse_input_values(content):
    f = dict()

    parser = BeautifulSoup(content, 'html.parser')
    ref = parser.findAll('input')

    for i in ref:
        if "xsrf" in i.get("name", "") or i.get("name", "") == "tid":
            f.update({i["name"]: i["value"]})
    
    return f


def login_process(__username, __password):
    """Login to Magenta TV via webpage using the email address as username"""

    session = dict()
    uu_id = str(uuid4())
    

    #
    # RETRIEVE SESSION DATA
    #

    # STEP 1: GET COOKIE TOKEN (GET REQUEST)
    url = "https://accounts.login.idm.telekom.com/oauth2/auth?client_id=10LIVESAM30000004901NGTVMAGENTA000000000&redirect_uri=https%3A%2F%2Fweb.magentatv.de%2Fauthn%2Fidm&response_type=code&scope=openid+offline_access"
    req = requests.get(url, headers=header)
    cookies = req.cookies.get_dict()

    # STEP 2: SEND USERNAME/MAIL 
    data = {"x-show-cancel": "false", "bdata": "", "pw_usr": __username, "pw_submit": "", "hidden_pwd": ""}
    data.update(parse_input_values(req.content))

    url_post = "https://accounts.login.idm.telekom.com/factorx"
    req = requests.post(url_post, cookies=cookies, data=data, headers=header)
    cookies = req.cookies.get_dict()

    # STEP 3: SEND PASSWORD
    data = {"hidden_usr": __username, "bdata": "", "pw_pwd": __password, "pw_submit": ""}
    data.update(parse_input_values(req.content))

    req = requests.post(url_post, cookies=cookies, data=data, headers=header)
    code = req.url.split("=")[1]

    # STEP 4: RETRIEVE ACCESS TOKEN FOR USER
    url = "https://accounts.login.idm.telekom.com/oauth2/tokens"
    data = {"scope": "openid", "code": code, "grant_type": "authorization_code", "redirect_uri": "https://web.magentatv.de/authn/idm", "client_id": "10LIVESAM30000004901NGTVMAGENTA000000000", "claims": '{"id_token":{"urn:telekom.com:all":{"essential":false}}}'}

    req = requests.post(url, cookies=cookies, data=data, headers=header)
    bearer = req.json()
    
    # STEP 5: UPDATE ACCESS TOKEN FOR TV/EPG
    data = {"scope": "ngtvepg", "grant_type": "refresh_token", "refresh_token": bearer["refresh_token"], "client_id": "10LIVESAM30000004901NGTVMAGENTA000000000"}

    req = requests.post(url, cookies=cookies, data=data, headers=header)
    bearer = req.json()
    
    # STEP 6: EPG GUEST AUTH - JSESSION
    url = "https://api.prod.sngtv.magentatv.de/EPG/JSON/Login?&T=Windows_chrome_86"
    data = {"userId": "Guest", "mac": "00:00:00:00:00:00"}

    req = requests.post(url, data=data, headers=header)
    j_session = req.cookies.get_dict()["JSESSIONID"]

    # STEP 7: EPG USER AUTH - ALL SESSIONS
    url = 'https://api.prod.sngtv.magentatv.de/EPG/JSON/Authenticate?SID=firstup&T=Windows_chrome_86'
    data = '{"terminalid":"' + uu_id + '","mac":"' + uu_id + '","terminaltype":"WEBTV","utcEnable":1,"timezone":"UTC","userType":3,"terminalvendor":"Unknown","preSharedKeyID":"PC01P00002","cnonce":"aa29eb89d78894464ab9ad3e4797eff6"}'
    epg_cookies = {"JSESSIONID": j_session}

    req = requests.post(url, data=data, headers=header, cookies=epg_cookies)
    epg_cookies = req.cookies.get_dict()

    # STEP 8: GET DEVICE ID TO ACCESS WIDEVINE DRM STREAMS
    x = 0
    while True:
        # 8.1: AUTHENTICATE
        url = "https://api.prod.sngtv.magentatv.de/EPG/JSON/DTAuthenticate"
        data = '{"areaid":"1","cnonce":"aa29eb89d78894464ab9ad3e4797eff6","mac":"' + uu_id + '","preSharedKeyID":"NGTV000001","subnetId":"4901","templatename":"NGTV","terminalid":"' + uu_id + '","terminaltype":"WEB-MTV","terminalvendor":"WebTV","timezone":"Europe/Berlin","usergroup":"OTT_NONDTISP_DT","userType":"1","utcEnable":1,"accessToken":"' + f'{bearer["access_token"]}' + '","caDeviceInfo":[{"caDeviceId":"' + uu_id + '","caDeviceType":8}],"connectType":1,"osversion":"Windows 10","softwareVersion":"1.45.1","terminalDetail":[{"key":"GUID","value":"' + uu_id + '"},{"key":"HardwareSupplier","value":"WEB-MTV"},{"key":"DeviceClass","value":"TV"},{"key":"DeviceStorage","value":0},{"key":"DeviceStorageSize","value":0}]}'

        req = requests.post(url, data=data, headers=header, cookies=epg_cookies)
        user_data = req.json()
        
        if "success" in user_data["retmsg"]:
            break
        
        # 8.2: RETRIEVE AVAILABLE WEBTV DEVICE
        url = "https://api.prod.sngtv.magentatv.de/EPG/JSON/GetDeviceList"
        data = '{"deviceType":"2;0;5;17","userid":"' + user_data["userID"] + '"}'

        req = requests.post(url, data=data, headers=header, cookies=epg_cookies)
        device_data = req.json()

        for i in device_data["deviceList"]:
            if i["deviceName"] == "WebTV":
                uu_id = i["physicalDeviceId"]
                break
        
        x = x + 1
        if x > 3:
            raise Exception("Error: Authentication failure")
             
    
    # SETUP SESSION
    session.update({"deviceId": req.json()["caDeviceInfo"][0]["VUID"]})  # DEVICE ID
    session.update({"cookies": req.cookies.get_dict()})  # EPG SESSION COOKIES
    
    # RETURN USER-SPECIFIC COOKIE VALUES
    return session


def get_channel_list(session):
    """Retrieve the Live TV channel list"""

    url = "https://api.prod.sngtv.magentatv.de/EPG/JSON/AllChannel"
    data = '{"channelNamespace":"12","filterlist":[{"key":"IsHide","value":"-1"}],"metaDataVer":"Channel/1.1","properties":[{"include":"/channellist/logicalChannel/contentId,/channellist/logicalChannel/name,/channellist/logicalChannel/chanNo,/channellist/logicalChannel/externalCode,/channellist/logicalChannel/categoryIds,/channellist/logicalChannel/introduce,/channellist/logicalChannel/pictures/picture/href,/channellist/logicalChannel/pictures/picture/imageType,/channellist/logicalChannel/physicalChannels/physicalChannel/mediaId,/channellist/logicalChannel/physicalChannels/physicalChannel/definition,/channellist/logicalChannel/physicalChannels/physicalChannel/externalCode,/channellist/logicalChannel/physicalChannels/physicalChannel/fileFormat","name":"logicalChannel"}],"returnSatChannel":0}'
    epg_cookies = session["cookies"]
    header.update({"X_CSRFToken": session["cookies"]["CSRFSESSION"]})

    req = requests.post(url, data=data, headers=header, cookies=epg_cookies)

    ch_list =  {i["contentId"]: {"name": i["name"], "img": i["pictures"][0]["href"]} for i in req.json()["channellist"]}
    
    request_string = ""
    for i in ch_list.keys():
        request_string = request_string + '{"channelId":"' + i + '","type":"VIDEO_CHANNEL"},'
    request_string = request_string[:-1]

    url = "https://api.prod.sngtv.magentatv.de/EPG/JSON/AllChannelDynamic"
    data = '{"channelIdList":[' + request_string + '],"channelNamespace":"12","filterlist":[{"key":"IsHide","value":"-1"}],"properties":[{"include":"/channelDynamicList/logicalChannelDynamic/contentId,/channelDynamicList/logicalChannelDynamic/physicalChannels/physicalChannelDynamic/mediaId,/channelDynamicList/logicalChannelDynamic/physicalChannels/physicalChannelDynamic/playurl,/channelDynamicList/logicalChannelDynamic/physicalChannels/physicalChannelDynamic/btvBR,/channelDynamicList/logicalChannelDynamic/physicalChannels/physicalChannelDynamic/btvCR,/channelDynamicList/logicalChannelDynamic/physicalChannels/physicalChannelDynamic/cpvrRecBR,/channelDynamicList/logicalChannelDynamic/physicalChannels/physicalChannelDynamic/cpvrRecCR,/channelDynamicList/logicalChannelDynamic/physicalChannels/physicalChannelDynamic/pltvCR,/channelDynamicList/logicalChannelDynamic/physicalChannels/physicalChannelDynamic/pltvBR,/channelDynamicList/logicalChannelDynamic/physicalChannels/physicalChannelDynamic/irCR,/channelDynamicList/logicalChannelDynamic/physicalChannels/physicalChannelDynamic/irBR,/channelDynamicList/logicalChannelDynamic/physicalChannels/physicalChannelDynamic/npvrRecBR,/channelDynamicList/logicalChannelDynamic/physicalChannels/physicalChannelDynamic/npvrRecCR,/channelDynamicList/logicalChannelDynamic/physicalChannels/physicalChannelDynamic/npvrOnlinePlayCR,/channelDynamicList/logicalChannelDynamic/physicalChannels/physicalChannelDynamic/npvrOnlinePlayBR","name":"logicalChannelDynamic"}]}'
    epg_cookies = session["cookies"]
    header.update({"X_CSRFToken": session["cookies"]["CSRFSESSION"]})

    req = requests.post(url, data=data, headers=header, cookies=epg_cookies)

    for i in req.json()["channelDynamicList"]:
        for p in i["physicalChannels"]:
            if ".mpd?" in p.get("playurl", ""):
                ch_list[i["contentId"]]["playurl"] = p["playurl"]

    return ch_list


def create_m3u(ch_list, session, directory):
    license_url = "https://vmxdrmfklb1.sfm.t-online.de:8063/"

    mapping_url = "https://github.com/sunsettrack4/config_files/raw/master/tkm_channels.json"
    mapping = requests.get(mapping_url).json()

    with open(f"{directory}/magenta.m3u", "w") as file:
         file.write("#EXTM3U\n")
         for i in ch_list.keys():
             if ch_list[i].get("playurl"):
                file.write("#KODIPROP:inputstreamclass=inputstream.adaptive\n")
                file.write("#KODIPROP:inputstream.adaptive.manifest_type=mpd\n")
                file.write("#KODIPROP:inputstream.adaptive.license_type=com.widevine.alpha\n")
                file.write(f"#KODIPROP:inputstream.adaptive.license_key={license_url}|deviceId={session['deviceId']}|R" + "{SSM}|\n")
                if mapping["channels"]["DE"].get(ch_list[i]["name"]):
                    file.write(f'#EXTINF:0001 tvg-id="{mapping["channels"]["DE"][ch_list[i]["name"]]}" tvg-logo="{ch_list[i]["img"]}", {ch_list[i]["name"]}\n')
                else:
                    file.write(f'#EXTINF:0001 tvg-id="{ch_list[i]["name"]}" tvg-logo="{ch_list[i]["img"]}", {ch_list[i]["name"]}\n')
                file.write(ch_list[i]["playurl"] + "\n")
