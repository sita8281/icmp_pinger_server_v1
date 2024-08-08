import browser
from browser import document, bind, ajax, html, timer
import datetime

api = None
id_timer = None

def create_table(response):
	hosts = response.json
	div_content = document['content']

	try:
		table = document['table1'].remove()
	except Exception:
		pass
	table = html.TABLE(Class='table', id='table1')
	thead = html.THEAD()
	thead <= html.TR(html.TH('Статус', id='status_col') + html.TH('Название', id='name_col') + html.TH('IP') + html.TH('Время изменения'))
	table <= thead

	tbody = html.TBODY()

	for host in hosts:
		if 'clock' in host[3]:
			img = 'images/clock.png'
		elif host[3] == 'online':
			img = 'images/icmp_good.png'
		elif host[3] == 'offline':
			img = 'images/icmp_bad.png'
		elif host[3] == 'pause':
			img = 'images/pause1.png'
		time_change = datetime.datetime.fromtimestamp(int(host[4])).strftime('%Y-%m-%d')
		date_change = datetime.datetime.fromtimestamp(int(host[4])).strftime('%H:%M:%S')
		tbody <= html.TR(html.TD(html.IMG(src=img)) + html.TD(host[1]) + html.TD(host[0]) + html.TD(time_change + ' ' + date_change))

	table <= tbody
	div_content <= table

	browser.console.log('12345')

	global id_timer

	id_timer = timer.set_timeout(update_table, 1000)


def update_table():
	if api:
		ajax.get(api, oncomplete=create_table, mode='json')


def get_all_hosts(ev):
	global api
	global id_timer
	if id_timer:
		timer.clear_timeout(id_timer)
	api = '/api/hosts/all'
	ajax.get('/api/hosts/all', oncomplete=create_table, mode='json')

def get_dead_hosts(ev):
	global api
	global id_timer
	if id_timer:
		timer.clear_timeout(id_timer)
	api = '/api/hosts/dead'
	ajax.get('/api/hosts/dead', oncomplete=create_table, mode='json')

def get_live_hosts(ev):
	global api
	global id_timer
	if id_timer:
		timer.clear_timeout(id_timer)
	api = '/api/hosts/live'
	ajax.get('/api/hosts/live', oncomplete=create_table, mode='json')

def get_pause_hosts(ev):
	global api
	global id_timer
	if id_timer:
		timer.clear_timeout(id_timer)
	api = '/api/hosts/pause'
	ajax.get('/api/hosts/pause', oncomplete=create_table, mode='json')

def check_all(ev):
	ajax.get('/api/check_all', oncomplete=lambda ev: browser.alert('Пинг всех хостов запущен..'), mode='json')

def check_dead(ev):
	ajax.get('/api/check_dead', oncomplete=lambda ev: browser.alert('Пинг мертвых хостов запущен..'), mode='json')

document['all_hosts'].bind('click', get_all_hosts)
document['live_hosts'].bind('click', get_live_hosts)
document['dead_hosts'].bind('click', get_dead_hosts)
document['pause_hosts'].bind('click', get_pause_hosts)
document['check_all'].bind('click', check_all)
document['check_dead'].bind('click', check_dead)

