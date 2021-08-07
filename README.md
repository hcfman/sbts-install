Hello
- Verify that it's uptodate
- Check that we are running read-write
- Install tomcat
- Modify tomcat
- Install clone branch of yolov3
- Install all the python modules
- Java installation
- Install apache
- Install letsencrypt
- Tweak /etc/rc.local


== Python requirements ==

apt install -y python3-numpy
apt install -y python3-pip
pip3 install flask
pip3 install requests
pip3 install websockets
pip3 install shapely

== Apache2 installation ==

apt install -y apache2

a2enmod rewrite
a2enmod headers
a2enmod proxy
a2enmod proxy_http
a2enmod proxy_balancer
a2enmod lbmethod_byrequests
a2enmod proxy_wstunnel

== Java installation ==

apt install -y openjdk-8-jdk
