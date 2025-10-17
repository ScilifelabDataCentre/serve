FROM alpine:3.22 AS sshprep
RUN apk add --no-cache openssh \
    && ssh-keygen -A

FROM runtime as local
USER root

RUN apk add --update --no-cache openssh

# Copy cleanly generated host keys from the pure Alpine stage
COPY --from=sshprep /etc/ssh /etc/ssh

# Your existing setup
RUN mkdir -p /root/.ssh \
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
    && echo 'GatewayPorts clientspecified' >> /etc/ssh/sshd_config \
    && sed -i '/UsePAM/d' /etc/ssh/sshd_config

RUN echo 'root:password' | chpasswd

EXPOSE 22
CMD ["/usr/sbin/sshd", "-D"]
