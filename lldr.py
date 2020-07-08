import cookielib
import os
import urllib
import urllib2
import sys
import config
import requests
import re
from bs4 import BeautifulSoup
from clint.textui import progress
import time

reload(sys)
sys.setdefaultencoding('utf-8')


def login():
    cookie_filename = 'cookies.txt'

    cookie_jar = cookielib.MozillaCookieJar(cookie_filename)

    opener = urllib2.build_opener(
                urllib2.HTTPRedirectHandler(),
                urllib2.HTTPHandler(debuglevel=0),
                urllib2.HTTPSHandler(debuglevel=0),
                urllib2.HTTPCookieProcessor(cookie_jar)
            )

    html = load_page(opener, 'https://www.linkedin.com/checkpoint/lg/login')
    soup = BeautifulSoup(html, 'html.parser')


    csrf = soup.find('input',{'name':'csrfToken'}).get('value')
    loginCsrfParam = soup.find('input',{'name':'loginCsrfParam'}).get('value')

    login_data = urllib.urlencode({
                    'session_key': config.USERNAME,
                    'session_password': config.PASSWORD,
                    'csrfToken': csrf,
                    'loginCsrfParam': loginCsrfParam
                })

    load_page(opener, 'https://www.linkedin.com/checkpoint/lg/login-submit', login_data)

    try:
        cookie = cookie_jar._cookies['.www.linkedin.com']['/']['li_at'].value
        jsessionid = ''
        for ck in cookie_jar:
            # print cookie.name, cookie.value, cookie.domain
            if ck.name == 'JSESSIONID':
                jsessionid = ck.value
    except Exception, e:
        print e
        sys.exit(0)

    cookie_jar.save()
    os.remove(cookie_filename)

    return cookie, csrf


def authenticate():
    try:
        session, jsessionid = login()
        if len(session) == 0:
            sys.exit('[!] Unable to login to LinkedIn.com')
        print '[*] Obtained new session: %s' % session
        cookies = dict(li_at=session, JSESSIONID=jsessionid)
    except Exception, e:
        sys.exit('[!] Could not authenticate to linkedin. %s' % e)
    return cookies


def load_page(opener, url, data=None):

    try:
        if data is not None:
            response = opener.open(url, data)
        else:
            response = opener.open(url)
        return ''.join(response.readlines())
    except Exception, e:
        print '[Notice] Exception hit'
        print e
        sys.exit(0)


def format_time(ms):
    seconds, milliseconds = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return '%d:%02d:%02d,%02d' % (hours, minutes, seconds, milliseconds)



def download_file(url, file_path, file_name):

    reply = requests.get(url, stream=True)
    if not os.path.exists(file_path):
        os.makedirs(file_path)
    with open(file_path + '/' + file_name, 'wb') as f:
        total_length = int(reply.headers.get('content-length'))
        for chunk in progress.bar(reply.iter_content(chunk_size=1024), expected_size=(total_length/1024) + 1):
            if chunk:
                f.write(chunk)
                f.flush()


def download_desc(desc, url, file_path, file_name):
    if not os.path.exists(file_path):
        os.makedirs(file_path)
    with open(file_path + '/' + file_name, 'wb') as f:
        f.write('%s\n\n%s' % (desc, url))


def download_sub(subs, path, file_name):
    with open(path + '/' + file_name, 'a') as f:
        i = 1
        for sub in subs:
            t_start = sub['transcriptStartAt']
            if i == len(subs):
                t_end = t_start + 5000
            else:
                t_end = subs[i]['transcriptStartAt']
            caption = sub['caption']
            f.write('%s\n' % str(i))
            f.write('%s --> %s\n' % (format_time(t_start), format_time(t_end)))
            f.write('%s\n\n' % caption)
            i += 1


def timestamp():
    print '[%s]' % time.ctime()


if __name__ == '__main__':
    cookies = authenticate()
    headers = {'Csrf-Token':cookies['JSESSIONID']}

    for course in config.COURSES:
        print ''
        course_url = 'https://www.linkedin.com/learning-api/detailedCourses' \
                     '??fields=videos&addParagraphsToTranscript=true&courseSlug={0}&q=slugs'.format(course)
        r = requests.get(course_url, cookies=cookies, headers=headers)
        print r
        base_path = config.DEFAULT_DOWNLOAD_PATH if config.DEFAULT_DOWNLOAD_PATH else 'out'
        course_data = r.json()['elements'][0]
        course_name = course_data['title']
        course_name = re.sub(r'[\\/*?:"<>|]', "", course_name)
        course_path = '%s/%s' % (base_path, course_name)
        chapters = course_data['chapters']
        description = course_data['description']
        exercises_list = course_data['exerciseFiles']
        timestamp()

        if config.DESCRIPTIONS:
            print 'Downloading course description'
            download_desc(description, 'https://www.linkedin.com/learning/%s' % course, course_path, 'About - %s.txt' % course_name)

        if config.EX_FILES:
            for exercise in exercises_list:
                try:
                    ex_name = exercise['name']
                    ex_url = exercise['url']
                except (KeyError, IndexError):
                    timestamp()
                    print 'Can\'t download an exercise file for course [%s]' % course_name
                else:
                    exercise_path = course_path + '/' + ex_name
                    if os.path.exists(exercise_path):
                        timestamp()
                        print '[!] ------ Skipping the exercise file "%s" because it already exists' % ex_name
                        continue
                    timestamp()
                    print 'Downloading Exercise Files'
                    download_file(ex_url, course_path, ex_name)

        timestamp()
        print '[*] Parsing "%s" course\'s chapters' % course_name
        print '[*] [%d chapters found]' % len(chapters)
        for chapter in chapters:
            chapter_name = re.sub(r'[\\/*?:"<>|]', "", chapter['title'])
            videos = chapter['videos']
            vc = 0

            timestamp()
            print '[*] --- Parsing "%s" chapters\'s videos' % chapter_name
            print '[*] --- [%d videos found]' % len(videos)
            for video in videos:
                video_name = re.sub(r'[\\/*?:"<>|]', "", video['title']).encode("utf-8", errors='ignore')
                video_slug = video['slug']
                video_url = 'https://www.linkedin.com/learning-api/detailedCourses' \
                            '?addParagraphsToTranscript=false&courseSlug={0}&q=slugs&resolution=_720&videoSlug={1}' \
                    .format(course, video_slug)
                chapter_path = '%s/%s' % (course_path, chapter_name)
                video_path = chapter_path + '/' + '%s. %s.mp4' % (str(vc), video_name)
                r = requests.get(video_url, cookies=cookies, headers=headers)
                vc += 1
                video_data = r.json()['elements'][0]
                if os.path.exists(video_path):
                    timestamp()
                    print '[!] ------ Skipping the video "%s", because it already exists' % video_name
                    vc += 1
                    continue
                try:
                    download_url = re.search('"progressiveUrl":"(.+)","expiresAt"', r.text).group(1)
                except Exception, e:
                    timestamp()
                    print '[!] ------ Can\'t download the video "%s".' % video_name
                    print e
                else:
                    timestamp()
                    print '[*] ------ Downloading video "%s"' % video_name
                    download_file(download_url, chapter_path, '%s. %s.mp4' % (str(vc), video_name))
                    if config.SUBS:
                        try:
                            subs = video_data['selectedVideo']['transcript']['lines']
                        except KeyError:
                            timestamp()
                            print 'No subtitles available'
                        else:
                            timestamp()
                            print 'Downloading subtitles'
                            download_sub(subs, chapter_path, '%s. %s.srt' % (str(vc), video_name))
