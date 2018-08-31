import os
import re
import time
import multiprocessing
from threading import Thread
from collections import defaultdict
import json

MEMORY_PATH = '/sys/fs/cgroup/memory/docker'
CPUACCT_PATH = '/sys/fs/cgroup/cpuacct/docker/'
PID_PATH = '/sys/fs/cgroup/devices/docker'
PATH_BW = "/proc/net/route"
IMAGE_PATH = '/var/lib/docker/containers/'
hostname = os.uname()[1]
container_names = []
pids = []
containers = defaultdict(lambda: defaultdict(str))
TOTAL_CPU = multiprocessing.cpu_count()
# get bandwidth of the server


def get_interface_speed():
    file_interfaces = open(PATH_BW)
    interfaces = re.findall('([a-z]+\d)\W(\d+\S+)', file_interfaces.read())
    interface = 'None'
    for i in interfaces:
        if i[1] == '00000000':
            interface = i[0]
    try:
        bandwidth_file = open(os.path.join('/sys/class/net/', interface, 'speed'))
        bandwidth_temp = int(bandwidth_file.read())
    except IOError:
        bandwidth_temp = 1000
    return bandwidth_temp


bandwidth = get_interface_speed()
# get container names


def get_containers():
        global container_names
        container_names = []
        for container_name in os.listdir(MEMORY_PATH):
                if os.path.isdir(os.path.join(MEMORY_PATH, container_name)):
                        container_names.append(container_name)
                        try:
                            file_pid = open(os.path.join(PID_PATH, container_name) + '/tasks', 'r')
                            containers[container_name]['pid'] = file_pid.readline().strip('\n')
                            file_pid.close()
                        except IOError:
                            get_containers()
        if not container_names:
            print "No containers found"
            exit(1)


get_containers()

# get the container statistics


def get_stats():
        for container_name in container_names:
                image_file = json.loads(open(os.path.join(IMAGE_PATH, container_name, 'config.v2.json')).read())
                containers[container_name]['Name'] = image_file['Config']['Labels']['MESOS_TASK_ID'].split('.')[0]
                mem_limit_file = open(os.path.join(MEMORY_PATH, container_name, 'memory.limit_in_bytes'))
                mem_usage_file = open(os.path.join(MEMORY_PATH, container_name, 'memory.usage_in_bytes'))
                mem_limit = float(mem_limit_file.read())
                mem_usage = float(mem_usage_file.read())
                containers[container_name]['memory'] = format((mem_usage/mem_limit)*100, '.1f')
                swp_limit_file = open('/proc/meminfo')
                swp_usage_file = open(os.path.join(MEMORY_PATH, container_name, 'memory.memsw.usage_in_bytes'))
                swp_limit = int(re.findall('SwapTotal:\s+(\d+)', swp_limit_file.read())[0])*1024
                swp_usage = abs(mem_usage-float(swp_usage_file.read()))
                containers[container_name]['swap'] = format((swp_usage / swp_limit) * 100, '.1f')
                process = Thread(target=cal_cpu_net, args=[container_name])
                process.start()
        process.join()

# function for running threads


def cal_cpu_net(container_name):

    path_cpu_stat = os.path.join(CPUACCT_PATH, container_name, 'cpuacct.stat')
    cpu_stat = open(path_cpu_stat)
    try:
        net_stat = open('/proc/%s/net/dev' % containers[container_name]['pid'], 'r')
    except IOError:
        get_containers()
        net_stat = open('/proc/%s/net/dev' % containers[container_name]['pid'], 'r')
    data = net_stat.read()
    net_info = (re.findall('\s+(\d+)(?:\s+\d+){7}\s+(\d+).*', data))
    old_rx_eth0 = int(net_info[0][0])
    old_rx_eth1 = int(net_info[1][0])
    old_tx_eth0 = int(net_info[0][1])
    old_tx_eth1 = int(net_info[1][1])
    total_usage_old = sum([float(k) for k in re.findall('(\d+)', cpu_stat.read())])
    cpu_stat.seek(0)
    net_stat.seek(0)
    time.sleep(1)
    cpu_percent = sum([float(k) for k in re.findall('(\d+)', cpu_stat.read())]) - total_usage_old
    # average cpu usage per second
    data = net_stat.read()
    net_info = (re.findall('\s+(\d+)(?:\s+\d+){7}\s+(\d+).*', data))
    rx_eth0 = int(net_info[0][0])-old_rx_eth0
    rx_eth1 = int(net_info[1][0])-old_rx_eth1
    tx_eth0 = int(net_info[0][1])-old_tx_eth0
    tx_eth1 = int(net_info[1][1])-old_tx_eth1
    rx_percent = format(float((rx_eth0 + rx_eth1))/(bandwidth*10486), '.1f')  # (1024*1024/100=10486)
    tx_percent = format(float((tx_eth0 + tx_eth1))/(bandwidth*10486), '.1f')

    containers[container_name]['cpu_percent'] = format(cpu_percent, '.1f')
    containers[container_name]['rx_percent'] = rx_percent
    containers[container_name]['tx_percent'] = tx_percent


def display():
    get_stats()
    os.system('clear')

    print('*****************************************************************************')
    print('  ID       CPU    Memory    Swap   PID     Rx    Tx   Name ')
    for name in container_names:
        print name[:7], ' ', containers[name]['cpu_percent'], '%', '  ', containers[name]['memory'], '%', ' ',\
            containers[name]['swap'], '% ', containers[name]['pid'], '  ', containers[name]['rx_percent'], '   ', \
            containers[name]['tx_percent'], '  ', containers[name]['Name']


while True:
    display()
