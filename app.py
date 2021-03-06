import database
from flask import Flask, redirect, render_template, request, url_for, session, g
import requests
import os

app = Flask(__name__)
app.secret_key = 'secret_zohar'

#engine = database.create_engine('sqlite:///music2.db', echo=False)
engine = database.create_engine(os.environ['DATABASE_URL'], echo=False)
database.Base.metadata.create_all(engine)
Session = database.sessionmaker(bind=engine)


@app.before_request
def before_request():
    g.user = None
    if 'user_id' in session:
        db_session = Session()
        user = database.get_user_by_id(db_session, session['user_id'])
        g.user = user
        db_session.close()


@app.route('/', methods=['GET'])
def index():
    is_valid_artist = request.args.get('valid_artist', default='true') == 'true'
    if not g.user:
        return redirect(url_for("connect_page"))
    db_session = Session()
    top_rated_albums = database.get_top_likes_albums(db_session)
    db_session.close()
    return render_template('index.html', is_valid_artist=is_valid_artist, top_rated_albums=top_rated_albums)


@app.route('/connect-page', methods=['GET'])
def connect_page():
    session.pop('user_id', None)
    login_failed = request.args.get('login_failed', default='false') == 'true'
    return render_template('connect.html', login_failed=login_failed)


@app.route('/connect', methods=['POST'])
def connect():
    session.pop('user_id', None)
    user_name = request.form["user-name"]
    password = request.form["psw"]
    db_session = Session()
    user = database.get_user_by_username(db_session, user_name)
    if user is not None and password == user.password:
        session['user_id'] = user.user_id
        db_session.close()
        return redirect(url_for("index"))
    else:
        return redirect(url_for("connect_page", login_failed='true'))


@app.route('/register-page', methods=["GET"])
def register_page():
    user_exist = request.args.get('user_exist', default='false') == 'true'
    return render_template('register.html', user_exist=user_exist)


@app.route('/register', methods=["POST"])
def register():
    user_name = request.form["user-name"]
    password = request.form["psw"]
    birthday = request.form["birthday"]
    country = request.form["country"]
    db_session = Session()
    if database.get_user_by_username(db_session, user_name) is None:
        database.add_user(db_session, user_name, password, birthday, country)
        db_session.close()
        return redirect(url_for("connect_page"))
    else:
        return redirect(url_for("register_page", user_exist='true'))


@app.route('/update', methods=["GET", 'POST'])
def update_profile():
    if not g.user:
        return redirect(url_for("connect_page"))
    old_username = g.user.username
    if request.method == 'POST':
        username = request.form['user-name']
        password = request.form['psw']
        birthday = request.form['birthday']
        country = request.form['country']
        db_session = Session()
        if old_username == username or database.get_user_by_username(db_session, username) is None:
            database.update_user(db_session, g.user.user_id, username, password, birthday, country)
            db_session.close()
            return redirect(url_for("index"))
        return redirect(url_for("update_profile", user_exist='true'))
    else:
        user_exist = request.args.get('user_exist', default='false') == 'true'
        return render_template('update.html', user_exist=user_exist)


@app.route('/albums', methods=['GET'])
def albums():
    if not g.user:
        return redirect(url_for("connect_page"))
    artist_name = request.args.get('artist').title()
    albums_resp = requests.get(f'http://theaudiodb.com/api/v1/json/1/searchalbum.php?s={artist_name}')
    albums_resp_json = albums_resp.json()
    artist_resp = requests.get(f'http://theaudiodb.com/api/v1/json/1/search.php?s={artist_name}')
    artist_resp_json = artist_resp.json()
    if albums_resp_json['album'] is None:
        return redirect(url_for('index', valid_artist='false'))
    albums = albums_resp_json['album']
    artist = artist_resp_json['artists']
    sorted_albums = sorted(albums, key=lambda k: k["intYearReleased"], reverse=True) 
    return render_template(
        'results.html', 
        ARTIST_NAME=artist_name, 
        all_albums=sorted_albums, 
        artist_info=artist,
    )


@app.route('/albums/<album_id>')
def album(album_id):
    if not g.user:
        return redirect(url_for("connect_page"))
    album_info = get_album_details_api(album_id)
    if album_info is None:
        return redirect(url_for('index'))
    tracks_info = get_album_tracks_api(album_id)
    like = request.args.get('like', default='false') == 'true'
    db_session = Session()
    if database.get_like_data(db_session, g.user.user_id, album_id):
        like = 'true'
    total_likes = database.album_likes_amount(db_session, album_id)
    db_session.close()
    return render_template(
        'album.html',
        album_info=album_info,
        tracks_info=tracks_info, 
        like=like,
        total_likes=total_likes
    )


def get_album_details_api(album_id):
    album_resp = requests.get(f'https://theaudiodb.com/api/v1/json/1/album.php?m={album_id}') 
    album_resp_json = album_resp.json()
    if album_resp_json['album'] is None:
        return None
    return album_resp_json['album'][0]


def get_album_tracks_api(album_id):
    tracks_resp = requests.get(f'https://theaudiodb.com/api/v1/json/1/track.php?m={album_id}')
    tracks_resp_json = tracks_resp.json()
    return tracks_resp_json['track']


@app.route('/like', methods=['POST'])
def like():
    if not g.user:
        return redirect(url_for("connect_page"))
    album_id = request.form["idalbum"]
    db_session = Session()
    album_info = get_album_details_api(album_id)
    name = album_info['strAlbum']
    artist = album_info['strArtist']
    year = album_info['intYearReleased']
    rate = album_info['intScore']
    image = album_info['strAlbumThumb']
    database.add_or_update_album(db_session, album_id, name, artist, year, rate, image)
    database.add_like_by_ids(db_session, g.user.user_id, album_id)
    db_session.close()
    return redirect(url_for('album', album_id=album_id, like="true"))


@app.route('/unlike', methods=['POST'])
def unlike():
    if not g.user:
        return redirect(url_for("connect_page"))
    album_id = request.form["idalbum"]
    db_session = Session()
    database.delete_like(db_session, g.user.user_id, album_id)
    return redirect(url_for('album', album_id=album_id, like="false"))


@app.route('/favorites', methods=['GET'])
def favorites():
    if not g.user:
        return redirect(url_for("connect_page"))
    db_session = Session()
    favorites = database.get_likes_albums_by_user_id(db_session, g.user.user_id)
    db_session.close()
    return render_template('favorites.html', favorites=favorites)


if __name__ == '__main__':
    app.run(debug=True)