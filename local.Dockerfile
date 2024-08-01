FROM runtime as local

USER root

RUN apk add --update --no-cache openssh

RUN ssh-keygen -A \
    && mkdir -p /root/.ssh \
    && touch /root/.ssh/authorized_keys \
    && chmod 700 /root/.ssh \
    && chmod 600 /root/.ssh/authorized_keys

COPY id_rsa.pub /root/.ssh/authorized_keys

RUN sed -i '/^AllowTcpForwarding/d' /etc/ssh/sshd_config \
    && sed -i '/^GatewayPorts/d' /etc/ssh/sshd_config \
    && echo "AllowTcpForwarding yes" >> /etc/ssh/sshd_config \
    && echo 'PermitRootLogin yes' >> /etc/ssh/sshd_config \
    && echo 'PermitEmptyPasswords yes' >> /etc/ssh/sshd_config \
    && echo 'PasswordAuthentication yes' >> /etc/ssh/sshd_config \
    && echo 'ChallengeResponseAuthentication no' >> /etc/ssh/sshd_config \
    && echo 'GatewayPorts clientspecified' >> /etc/ssh/sshd_config

RUN sed -i '/UsePAM/d' /etc/ssh/sshd_config

# Set root password (optional, for testing purposes)
RUN echo 'root:password' | chpasswd

EXPOSE 22

CMD ["/usr/sbin/sshd", "-D"]
