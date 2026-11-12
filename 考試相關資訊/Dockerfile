# =============================================================================
#  srecruit-demo — the pre-exam practice environment (doc/demo/)
#
#  One image for all three practices, at the same paths doc/demo/ names:
#    /demo/section2-1   ros2 CLI practice      (ROS 2 Jazzy, rclpy)
#    /demo/section2-2   bitwise + PIO reading  (cc)
#    /demo/section2-3   pthread + DMA concepts (gcc, make)
#
#  Standalone on purpose: no pico-sdk, no cross toolchain, no judge, and not part
#  of docker/build.sh's chain. The build context is this folder alone, so nothing
#  else in the repo can reach the image and it can be handed out before the exam.
#  No board and no --privileged needed.
#
#  Build context = this folder:
#      docker build -t srecruit-demo demo/
#
#  Run (the 2-1 practice needs three shells in one container):
#      docker run --rm -it --name srecruit-demo srecruit-demo
#      docker exec -it srecruit-demo bash     # each extra terminal
#
#  Files live in the container and go away with --rm; to keep edits, bind-mount
#  a practice folder over its path with -v.
#
#  DEMO_BASE_IMAGE overrides the upstream base — point it at a registry mirror
#  when Docker Hub is unreachable.
# =============================================================================
ARG DEMO_BASE_IMAGE=ros:jazzy-ros-core
FROM ${DEMO_BASE_IMAGE}

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev make \
    && rm -rf /var/lib/apt/lists/*

COPY . /demo

# The base's entrypoint sources ROS only for the first shell; `docker exec`
# bypasses it, so extra terminals get ROS from .bashrc.
RUN echo 'source /opt/ros/jazzy/setup.bash' >> /root/.bashrc

WORKDIR /demo
CMD ["bash"]
