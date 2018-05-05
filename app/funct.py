# -*- coding: utf-8 -*-"
import cgi
import os, sys
import paramiko
import http.cookies
from paramiko import SSHClient
from datetime import datetime
from pytz import timezone
from configparser import ConfigParser, ExtendedInterpolation

path_config = "haproxy-webintarface.config"
config = ConfigParser(interpolation=ExtendedInterpolation())
config.read(path_config)

form = cgi.FieldStorage()
serv = form.getvalue('serv')
fullpath = config.get('main', 'fullpath')
time_zone = config.get('main', 'time_zone')
proxy = config.get('main', 'proxy')
ssh_keys = config.get('ssh', 'ssh_keys')
ssh_user_name = config.get('ssh', 'ssh_user_name')
haproxy_configs_server = config.get('configs', 'haproxy_configs_server')
hap_configs_dir = config.get('configs', 'haproxy_save_configs_dir')
haproxy_config_path  = config.get('haproxy', 'haproxy_config_path')
tmp_config_path = config.get('haproxy', 'tmp_config_path')
restart_command = config.get('haproxy', 'restart_command')

def check_config():
	for section in [ 'main', 'configs', 'ssh', 'logs', 'haproxy' ]:
		if not config.has_section(section):
			print('<center><div class="alert alert-danger">Check config file, no %s section</div>' % section)
			
def get_data(type):
	now_utc = datetime.now(timezone(time_zone))
	if type == 'config':
		fmt = "%Y-%m-%d.%H:%M:%S"
	if type == 'logs':
		fmt = '%Y%m%d'
	return now_utc.strftime(fmt)
			
def logging(serv, action):
	import sql
	dateFormat = "%b  %d %H:%M:%S"
	now_utc = datetime.now(timezone(time_zone))
	IP = cgi.escape(os.environ["REMOTE_ADDR"])
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_uuid = cookie.get('uuid')
	login = sql.get_user_name_by_uuid(user_uuid.value)
	mess = now_utc.strftime(dateFormat) + " from " + IP + " user: " + login + " " + action + " for: " + serv + "\n"
	log_path = config.get('main', 'log_path')
	
	try:		
		log = open(log_path + "/config_edit-"+get_data('logs')+".log", "a")
		log.write(mess)
		log.close
	except IOError:
		print('<center><div class="alert alert-danger">Can\'t read write log. Please chech log_path in config</div></center>')
		pass
	
	if config.get('telegram', 'enable') == "1": telegram_send_mess(mess)

def telegram_send_mess(mess):
	import telegram
	token_bot = config.get('telegram', 'token')
	channel_name = config.get('telegram', 'channel_name')
	
	if proxy is not None:
		pp = telegram.utils.request.Request(proxy_url=proxy)
	bot = telegram.Bot(token=token_bot, request=pp)
	bot.send_message(chat_id=channel_name, text=mess)
	
def check_login(**kwargs):
	import sql
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_uuid = cookie.get('uuid')
	ref = os.environ.get("SCRIPT_NAME")

	if user_uuid is not None:
		if sql.get_user_name_by_uuid(user_uuid.value) is None:
			print('<meta http-equiv="refresh" content="0; url=login.py?ref=%s">' % ref)
	else:
		print('<meta http-equiv="refresh" content="0; url=login.py?ref=%s">' % ref)
				
def is_admin(**kwargs):
	import sql
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	try:
		role = sql.get_user_role_by_uuid(user_id.value)
	except:
		role = 3
		pass
	level = kwargs.get("level")
		
	if level is None:
		level = 1
		
	try:
		if role <= level:
			return True
		else:
			return False
	except:
		return False
		pass

def page_for_admin(**kwargs):
	give_level = kwargs.get("level")
	
	if give_level is None:
		give_level = 1
	
	if not is_admin(level = give_level):
		print('<center><h3 style="color: red">How did you get here?! O_o You do not have need permissions</h>')
		print('<meta http-equiv="refresh" content="10; url=/">')
		import sys
		sys.exit()
		
def get_button(button, **kwargs):
	value = kwargs.get("value")
	if value is None:
		value = ""
	print('<button type="submit" value="%s" name="%s" class="btn btn-default">%s</button>' % (value, value, button))
		
def ssh_connect(serv, **kwargs):
	ssh = SSHClient()
	ssh.load_system_host_keys()
	ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
	try:
		if config.get('ssh', 'ssh_keys_enable') == "1":
			k = paramiko.RSAKey.from_private_key_file(ssh_keys)
			ssh.connect(hostname = serv, username = ssh_user_name, pkey = k )
		else:
			ssh.connect(hostname = serv, username = ssh_user_name, password = config.get('ssh', 'ssh_pass'))
		if kwargs.get('check'):
			return True
		else:
			return ssh
	except paramiko.AuthenticationException:
		print('<div class="alert alert-danger">Authentication failed, please verify your credentials</div>')
		return False
	except paramiko.SSHException as sshException:
		print('<div class="alert alert-danger">Unable to establish SSH connection: %s </div>' % sshException)
		return False
	except paramiko.BadHostKeyException as badHostKeyException:
		print('<div class="alert alert-danger">Unable to verify server\'s host key: %s </div>' % badHostKeyException)
		return False
	except Exception as e:
		if e.args[1] == "No such file or directory":
			print('<div class="alert alert-danger">{}. Check ssh key</div>'.format(e.args[1]))	
		elif e.args[1] == "Invalid argument":
			print('<div class="alert alert-danger">Check the IP of the new server</div>')
		else:
			print('<div class="alert alert-danger">{}</div>'.format(e.args[1]))	
		return False

def get_config(serv, cfg, **kwargs):
	if kwargs.get("keepalived"):
		config_path = "/etc/keepalived/keepalived.conf"
	else:
		config_path = haproxy_config_path
		
	ssh = ssh_connect(serv)
	try:
		sftp = ssh.open_sftp()
		sftp.get(config_path, cfg)
		sftp.close()
		ssh.close()
	except Exception as e:
		print('<center><div class="alert alert-danger">' + str(e) + ' Please check IP, and SSH settings</div>')
		sys.exit()
	
def show_config(cfg):
	print('<div style="margin-left: 16%" class="configShow">')
	try:
		conf = open(cfg, "r")
	except IOError:
		print('<div class="alert alert-danger">Can\'t read import config file</div>')
	i = 0
	for line in conf:
		i = i + 1
		if not line.find("global"):
			print('<span class="param">' + line + '</span><div>')
			continue
		if not line.find("defaults"):
			print('</div><span class="param">' + line + '</span><div>')
			continue
		if not line.find("listen"):
			print('</div><span class="param">' + line + '</span><div>')
			continue
		if not line.find("frontend"):
			print('</div><span class="param">' + line + '</span><div>')
			continue
		if not line.find("backend"):
			print('</div><span class="param">' + line + '</span><div>')
			continue
		if "acl" in line or "option" in line or "server" in line:
			if "timeout" not in line and "default-server" not in line and "#use_backend" not in line:
				print('<span class="paramInSec"><span class="numRow">')
				print(i)
				print('</span>' + line + '</span><br />')
				continue
		if "#" in line:
			print('<span class="comment"><span class="numRow">')
			print(i)
			print(line + '</span></span><br />')
			continue	
		if line.__len__() < 1:
			print('</div>')
		if line.__len__() > 1:
			print('<span class="configLine"><span class="numRow">')
			print(i)
			print('</span>' + line + '</span><br />')					
	print('</div></div>')
	conf.close

def install_haproxy(serv):
	script = "install_haproxy.sh"
	os.system("cp scripts/%s ." % script)
	if proxy is not None:
		proxy_serv = proxy
	else:
		proxy_serv = ""
	commands = [ "chmod +x "+tmp_config_path+script, tmp_config_path+script +" " + proxy_serv]
	
	upload(serv, tmp_config_path, script)	
	ssh_command(serv, commands)
	
	os.system("rm -f %s" % script)
	
def upload(serv, path, file, **kwargs):
	full_path = path + file
	
	try:
		ssh = ssh_connect(serv)
	except Exception as e:
		print('<div class="alert alert-danger">Connect fail: %s</div>' % e)
	try:
		sftp = ssh.open_sftp()
		file = sftp.put(file, full_path)
		sftp.close()
		ssh.close()
	except Exception as e:
		print('<div class="alert alert-danger">Upload fail: %s</div>' % e)
	
def upload_and_restart(serv, cfg, **kwargs):
	tmp_file = tmp_config_path + "/" + get_data('config') + ".cfg"
	
	try:
		ssh = ssh_connect(serv)
	except:
		print('<center><div class="alert alert-danger">Connect fail</div>')
	sftp = ssh.open_sftp()
	sftp.put(cfg, tmp_file)
	sftp.close()
	if kwargs.get("keepalived") == 1:
		if kwargs.get("just_save") == "save":
			commands = [ "mv -f " + tmp_file + " /etc/keepalived/keepalived.conf" ]
		else:
			commands = [ "mv -f " + tmp_file + " /etc/keepalived/keepalived.conf", "systemctl restart keepalived" ]
	else:
		if kwargs.get("just_save") == "save":
			commands = [ "/sbin/haproxy  -q -c -f " + tmp_file + "&& mv -f " + tmp_file + " " + haproxy_config_path ]
		else:
			commands = [ "/sbin/haproxy  -q -c -f " + tmp_file + "&& mv -f " + tmp_file + " " + haproxy_config_path + " && " + restart_command ]	
		try:
			if config.get('haproxy', 'firewall_enable') == "1":
				commands.extend(open_port_firewalld(cfg))
		except:
			return 'Please check the config for the presence of the parameter - "firewall_enable". Mast be: "0" or "1". Firewalld configure not working now'
			
	for command in commands:
		stdin, stdout, stderr = ssh.exec_command(command)

	return stderr.read().decode(encoding='UTF-8')

	ssh.close()
		
def open_port_firewalld(cfg):
	try:
		conf = open(cfg, "r")
	except IOError:
		print('<div class="alert alert-danger">Can\'t read export config file</div>')
	
	firewalld_commands = []
	
	for line in conf:
		if "bind" in line:
			bind = line.split(":")
			bind[1] = bind[1].strip(' ')
			bind = bind[1].split("ssl")
			bind = bind[0].strip(' \t\n\r')
			firewalld_commands.append('firewall-cmd --zone=public --add-port=%s/tcp --permanent' % bind)
				
	firewalld_commands.append('firewall-cmd --reload')
	return firewalld_commands
	
def check_haproxy_config(serv):
	commands = [ "/sbin/haproxy  -q -c -f %s" % haproxy_config_path ]
	ssh = ssh_connect(serv)
	for command in commands:
		stdin , stdout, stderr = ssh.exec_command(command)
		if not stderr.read():
			return True
		else:
			return False
	ssh.close()
	
def compare(stdout):
	i = 0
	minus = 0
	plus = 0
	total_change = 0
	
	print('</center><div class="out">')
	print('<div class="diff">')
		
	for line in stdout:
		i = i + 1

		if i is 1:
			print('<div class="diffHead">' + line + '<br />')
		elif i is 2:
			print(line + '</div>')
		elif line.find("-") == 0 and i is not 1:
			print('<div class="lineDiffMinus">' + line + '</div>')
			minus = minus + 1
		elif line.find("+") == 0 and i is not 2:
			print('<div class="lineDiffPlus">' + line + '</div>')	
			plus = plus + 1					
		elif line.find("@") == 0:
			print('<div class="lineDog">' + line + '</div>')
		else:
			print('<div class="lineDiff">' + line + '</div>')				
			
		total_change = minus + plus
	print('<div class="diffHead">Total change: %s, additions: %s & deletions: %s </div>' % (total_change, minus, plus))	
	print('</div></div>')
		
def show_log(stdout):
	i = 0
	for line in stdout:
		i = i + 1
		if i % 2 == 0: 
			print('<div class="line3">' + line + '</div>')
		else:
			print('<div class="line">' + line + '</div>')
			
def show_ip(stdout):
	for line in stdout:
		print(line)
		
def server_status(stdout):
	proc_count = ""
	i = 0
	for line in stdout.read().decode(encoding='UTF-8'):
		i = i + 1
		if i == 1:
			proc_count += line
			if line.find("0"):
				err = 1
			else:
				err = 0
			
	if err != 0:
		print('<span class="serverUp"> UP</span> running %s processes' % proc_count)
	else:
		print('<span class="serverDown"> DOWN</span> running %s processes' % proc_count)	

def ssh_command(serv, commands, **kwargs):
	ssh = ssh_connect(serv)
		  
	for command in commands:
		try:
			stdin, stdout, stderr = ssh.exec_command(command)
		except:
			continue
				
		if kwargs.get("ip") == "1":
			show_ip(stdout)
		elif kwargs.get("compare") == "1":
			compare(stdout)
		elif kwargs.get("show_log") == "1":
			show_log(stdout)
		elif kwargs.get("server_status") == "1":
			server_status(stdout)
		else:
			print('<div style="margin: -10px;">'+stdout.read().decode(encoding='UTF-8')+'</div>')
			
		print(stderr.read().decode(encoding='UTF-8'))
		
	ssh.close()

