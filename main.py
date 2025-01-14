"""
This is the main script. Pick provides a small CLI.
"""

from pathlib import Path
from datetime import datetime
from itertools import dropwhile, takewhile
import sys
import pandas as pd
from pick import pick
import instaloader
from instaloader import Profile, InstaloaderException
import logging

logging.basicConfig(filename='log.log', encoding='utf-8', level=logging.INFO)


def query_yes_no(question, default="yes"):
    """Ask yes/no question"""
    valid = {"yes": True, "y": True, "ye": True,
             "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' "
                             "(or 'y' or 'n').\n")


def do_login(L):
    """wrapper for instagram login"""
    username = input('What is your Instagram username?')
    try:
        # L.interactive_login(username)
        L.load_session_from_file("humandatascientist")
    except Exception as err:
        logging.error(err)
        do_login(L)
        

def choose_target(login):
    """Uses chooses which type of content to query."""
    nologin_targets = ['public profile', 'hashtag', 'single post']
    login_targets = ['private profile', 'location id',
                     'story', 'feed', 'saved']
    target_options = nologin_targets
    if login:
        # Make more options available
        target_options.extend(login_targets)
    titel = '''Please choose target.
See https://instaloader.github.io/basic-usage.html#what-to-download'''
    option, _ = pick(target_options, titel)
    return option


def get_instaloder_options():
    """Lets user select what they want to download"""
    options = ['pictures', 'videos', 'thumbnails']
    title = 'Which of these media do you want to download? (SPACE to mark)'
    selected = pick(options, title, multi_select=True)
    selected = [s[0] for s in selected]      
    return selected


def period_reduce():
    """Only downloads for a specific period. Doesnt work very well."""
    date_entry1 = input('Enter a "since" date in YYYY-MM-DD format. ')
    date_entry2 = input('Enter a "until" date in YYYY-MM-DD format. ')
    try:
        SINCE = datetime.strptime(date_entry1, '%Y-%m-%d')
        UNTIL = datetime.strptime(date_entry2, '%Y-%m-%d')
    except ValueError:
        logging.error("Invald date. Try again.\n")
        return period_reduce()
    logging.info('\nBeginning harvest...\n\n')
    limited_posts = takewhile(lambda p: p.date > UNTIL,
                              dropwhile(lambda p: p.date > SINCE,
                                        posts))
    return limited_posts


def parse_locations(row):
    """Turn location objects into dictionary for tabular representation."""
    if row and not pd.isna(row):
        return {
            'loc_id': row.id,
            'loc_lat': row.lat,
            'loc_lng': row.lng,
            'loc_name': row.name,
        }
    else:
        return ''


def ask_n_post_lim():
    """Ask user post limit"""
    n_post_lim = input("How many posts? ")
    try:
        result = int(n_post_lim)
    except ValueError:
        print("Please input an integer")
        return ask_n_post_lim()
    return result


# What do you want to download?
selected = get_instaloder_options()
if 'pictures' in selected:
    pictures = True
else:
    pictures = False
if 'videos' in selected:
    videos = True
else:
    videos = False
if 'thumbnails' in selected:
    thumbnails = True
else:
    thumbnails = False

# Do you want comments
get_comments = query_yes_no("Do you want download comments?", default="yes")

# Do you want to compress?
compress = query_yes_no("Do you want to compress jsons?", default="yes")

# Do you want to log in?
LOGIN = query_yes_no("Do you want to log in?", default="no")

# Initiatilize instaloader with user settings
L = instaloader.Instaloader(download_pictures=pictures,
                            download_videos=videos,
                            download_video_thumbnails=thumbnails,
                            compress_json=compress,
                            dirname_pattern='output/{target}',
                            filename_pattern='{shortcode}')

if LOGIN:
    do_login(L)

# Chose target (like hashtag, profile), based on whether logged in
target = choose_target(LOGIN)

# What do you want to query for?
query_inp = input(f'''Which {target} do you want to search for? 
Comma seperate if multiple like nature,climate,weather\n''')
queries = query_inp.split(',') 

# Only in time period?
period_only = query_yes_no('''
Do you want to limit your search to a specific period?
(Experimental)''',
                           default="no")

# Only n posts?
n_post_lim = None  # Default
n_post_only = query_yes_no("Do you want to limit your search to N number of posts?",
                           default="no")
if n_post_only:
    n_post_lim = ask_n_post_lim()

# These are the post attributes that will become dataframe columns
post_attr = [
    'shortcode',
    'mediaid',
    'owner_username',
    'owner_id',
    'date_local',
    'date_utc',
    'url',
    'typename',
    'caption',
    'caption_hashtags',
    'caption_mentions',
    'pcaption',
    'tagged_users',
    'video_url',
    'video_view_count',
    'likes',
    'comments',
    'location'
]

for query in queries:
    # Get posts based on user settings
    if target == 'public profile':
        profile = Profile.from_username(L.context, query)
        posts = profile.get_posts()
    if target == 'hashtag':
        # posts = L.get_hashtag_posts(query)
        posts = instaloader.NodeIterator(
            L.context, "9b498c08113f1e09617a1703c22b2f32",
            lambda d: d['data']['hashtag']['edge_hashtag_to_media'],
            lambda n: instaloader.Post(L.context, n),
            {'tag_name': query},
            f"https://www.instagram.com/explore/tags/{query}/"
        )
    if target == 'location id':
        posts = L.get_location_posts(query)

    # Initialize main dataframe and comment list
    data = pd.DataFrame(columns=post_attr)
    all_comments = []

    # Download data
    while True:
        try:
            # Apply time limit to post generator
            if period_only:
                posts = period_reduce()

            # Apply n limit to post generator, like posts[:n_post_lim]
            if n_post_only:
                posts = (x for _, x in zip(range(n_post_lim), posts))

            print(f'\nNow harvesting {query}. Ctrl-C to stop.\n\n')
            try:
                for post in posts:
                    try:
                        L.download_post(post, target=query)
                        post_info = []
                        for attr in post_attr:
                            attribute = ''
                            try:
                                attribute = getattr(post, attr)
                            except:
                                print(f'\n Could not get {attr} for a post...')
                            else:
                                post_info.append(attribute)


                        # Put postinfo in dataframe
                        data = data.append(pd.Series(
                            dict(zip(data.columns, post_info))),
                                        ignore_index=True)
                    except Exception as e:
                        logging.error(e)
                    

                    # Get comments
                    if get_comments and post.comments > 0:
                        for comment in post.get_comments():
                            all_comments.append({
                                'post_shortcode': post.shortcode,
                                'answer_to_comment': '',
                                'created_at_utc': comment.created_at_utc,
                                'id': comment.id,
                                'likes_count': comment.likes_count,
                                'owner': comment.owner.userid,
                                'text': comment.text})
                            if hasattr(comment, 'answers'):
                                for answer in comment.answers:
                                    all_comments.append({
                                        'post_shortcode': post.shortcode,
                                        'answer_to_comment': comment.id,
                                        'created_at_utc': answer.created_at_utc,
                                        'id': answer.id,
                                        'likes_count': answer.likes_count,
                                        'owner': answer.owner.userid,
                                        'text': answer.text})
                break
            except (TypeError) as e:
                logging.error(e)
        except (KeyboardInterrupt, InstaloaderException) as e:
            logging.error(e)
            break

    def join_iterable(lst):
        if lst is None or lst == 0:
            return
        if isinstance(lst, str):
            return lst
        else:
            return ','.join(lst) 

    # Turn list columns into strings
    data[['caption_hashtags',
          'caption_mentions',
          'tagged_users']] = data[[
              'caption_hashtags',
              'caption_mentions',
              'tagged_users']].applymap(join_iterable)

    # Turn location column into dicts, then seperate columns
    data['location'] = data['location'].apply(parse_locations)
    data = pd.concat([data, data['location'].apply(pd.Series)], axis=1)
    data = data.drop('location', errors='ignore')

    # Make comments dataframe
    comments_df = pd.DataFrame(all_comments)

    # Save data and comments
    outpath = Path(f'output/{query}')
    outpath.mkdir(exist_ok=True)

    data_filepath = f'{outpath}/{query}.csv'
    comments_filepath = f'{outpath}/{query}_comments.csv'

    data.to_csv(data_filepath, index=False)
    comments_df.to_csv(comments_filepath)
