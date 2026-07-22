FROM wurstmeister/kafka

ADD https://repo1.maven.org/maven2/io/prometheus/jmx/jmx_prometheus_javaagent/0.20.0/jmx_prometheus_javaagent-0.20.0.jar /opt/jmx-exporter/jmx_prometheus_javaagent.jar
COPY kafka-jmx-exporter.yml /opt/jmx-exporter/kafka-jmx-exporter.yml
