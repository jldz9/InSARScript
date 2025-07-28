FROM ubuntu:22.04

# Set the non-root username and group
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID
ENV SHELL=/bin/bash
# Create the user
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && apt-get update \
    && apt-get install -y \
    sudo \
    wget \
    curl \
    bash \
    && rm -rf /var/lib/apt/lists/* \
    && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

RUN ln -sf /bin/bash /bin/sh
RUN chown -R $USERNAME /home/vscode
CMD ["/bin/bash", "-c"]
EXPOSE 3000 8080 8081 8082
# Get Miniconda
USER $USERNAME
RUN wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /home/vscode/miniconda.sh \
    && chmod +x /home/vscode/miniconda.sh \
    && bash /home/vscode/miniconda.sh -b -u -p /home/vscode/miniconda3 
ENV PATH=/home/vscode/miniconda3/bin:$PATH
RUN /home/vscode/miniconda3/bin/conda init bash
RUN /home/vscode/miniconda3/bin/conda update conda -y
RUN wget https://raw.githubusercontent.com/jldz9/geodlkit/refs/heads/master/environment.yml -O /home/vscode/environment.yml
RUN /home/vscode/miniconda3/bin/conda env update --name base -f /home/vscode/environment.yml
RUN /home/vscode/miniconda3/bin/conda update -n base -c defaults conda -y
RUN pip install geodlkit





