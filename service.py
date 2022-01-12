from resources.lib import connect
import xbmcaddon, xbmcgui


__addon__ = xbmcaddon.Addon()
__addonname__ = __addon__.getAddonInfo('name')

__login = __addon__.getSetting("username")
__password = __addon__.getSetting("password")

directory = __addon__.getSetting("folder")
notification = __addon__.getSetting("notification")

def run():
    if __login and __password and directory:
        try:
            session = connect.login_process(__login, __password)
        except:
            xbmcgui.Dialog().notification(__addonname__, "Authentication failed, please check your credentials.", xbmcgui.NOTIFICATION_ERROR)
            session = False
        if session:
            ch_list = connect.get_channel_list(session)
            connect.create_m3u(ch_list, session, directory)
            if notification == "true":
                xbmcgui.Dialog().notification(__addonname__, "M3U Playlist created successfully!", xbmcgui.NOTIFICATION_INFO)
    else:
        xbmcgui.Dialog().notification(__addonname__, "Please add your credentials and the file directory in addon settings.", xbmcgui.NOTIFICATION_ERROR)

if __name__ == "__main__":
    run()