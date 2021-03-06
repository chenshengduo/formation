#!/usr/bin/env python

import rospy

from std_msgs.msg import Empty, Int32, Float32
from geometry_msgs.msg import Point
from formation.msg import RobotFormationState, FormationPositions, RobotTarget
import pymavlink.mavutil as mavutil

from threading import Thread

from time import sleep

class MasterBridge():

	def __init__(self):

		self.DEBUG					= rospy.get_param("DEBUG", False)

		self.ENABLE_MASTER_GCS		= rospy.get_param("USE_MASTER_AS_GCS", False)

		# If True, connection will be over serial, otherwise will be over UDP
		self.USE_SERIAL				= rospy.get_param("USE_SERIAL", False)
		
		self.n 						= rospy.get_param("nRobots", 5)
		if self.DEBUG:
			rospy.logwarn("[Master]: Got number of robots = %s", self.n)

		self.master_sys_id			= rospy.get_param("master_sys_id", 255)
		if self.DEBUG:
			rospy.logwarn("Master MAVLink ID = %s", self.master_sys_id)

		# pymavlink connection
		self.master_udp				= rospy.get_param("master_udp", "127.0.0.1:30000")
		self.master_serial			= rospy.get_param("master_serial", "/dev/ttyUSB0")
		self.serial_baud			= rospy.get_param("serial_baud", 57600)

		if self.USE_SERIAL:
			self.mav				= mavutil.mavlink_connection(self.master_serial, baud=self.serial_baud, source_system=self.master_sys_id)
			if self.DEBUG:
				rospy.logwarn("Master is connected on udpout:%s", self.master_serial)
		else:
			self.mav				= mavutil.mavlink_connection("udpout:"+self.master_udp, source_system=self.master_sys_id)
			if self.DEBUG:
				rospy.logwarn("Master is connected on udpout:%s", self.master_udp)

		self.ROBOT_STATE			= 1
		self.MASTER_CMD				= 2
		self.MASTER_CMD_ARM			= 3
		self.MASTER_CMD_TKO			= 4
		self.MASTER_CMD_LAND		= 5
		self.MASTER_CMD_POSCTL		= 6
		self.MASTER_CMD_HOLD		= 7
		self.MASTER_CMD_SHUTDOWN	= 8
		self.MASTER_CMD_REBOOT		= 9
		self.MASTER_CMD_SET_ORIGIN	= 10
		self.MASTER_CMD_SET_EAST	= 11
		self.MASTER_CMD_SET_nROBOTS	= 12
		self.MASTER_CMD_GO			= 13
		self.MASTER_CMD_GOAL		= 14
		self.MASTER_CMD_SET_TOALT	= 15
		self.MASTER_CMD_ACK			= 16

		# CMD string
		self.CMD_STRING				= {3:'MASTER_CMD_ARM', 4:'MASTER_CMD_TKO', 5:'MASTER_CMD_LAND', 6:'MASTER_CMD_POSCTL', 7:'MASTER_CMD_HOLD', 8:'MASTER_CMD_SHUTDOWN', 9:'MASTER_CMD_REBOOT', 10:'MASTER_CMD_SET_ORIGIN', 11:'MASTER_CMD_SET_EAST', 12:'MASTER_CMD_SET_nROBOTS', 13:'MASTER_CMD_GO', 14:'MASTER_CMD_GOAL', 15:'MASTER_CMD_SET_TOALT'}

		# Topics names of robots locations in local defined ENU coordiantes
		self.r_loc_topic_names = []
		rstr = "/robot"
		for i in range(self.n):
			self.r_loc_topic_names.append(rstr+str(i)+"/state")

		# Subscribers
		rospy.Subscriber('/arm_robot', Int32, self.armCb)
		rospy.Subscriber('/disarm_robot', Int32, self.disarmCb)
		rospy.Subscriber('/takeoff_robot', Int32, self.tkoCb)
		rospy.Subscriber('/land_robot', Int32, self.landCb)
		rospy.Subscriber('/hold_robot', Int32, self.holdCb)
		rospy.Subscriber('/posctl_robot', Int32, self.posctlCb)

		rospy.Subscriber('/shutdown_robot', Int32, self.shutdownCb)
		rospy.Subscriber('/reboot_robot', Int32, self.rebootCb)

		rospy.Subscriber('/formation', FormationPositions, self.formationCb)
		rospy.Subscriber('/go', Empty, self.goCb)

		rospy.Subscriber('/setnRobots', Int32, self.nRCb)
		rospy.Subscriber('/setOrigin', Point, self.setOriginCb)
		rospy.Subscriber('/setEast', Point, self.setEastCb)
		rospy.Subscriber("/setTOALT", Float32, self.setTOALTCb)


		# Publishers
		self.robot_state_pub_list = []
		for i in range(self.n):
			self.robot_state_pub_list.append(rospy.Publisher(self.r_loc_topic_names[i], RobotFormationState, queue_size=1))

	def send_heartbeat(self):
		""" Sends heartbeat msg to all vehicles
		"""
		self.mav.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, 0, mavutil.mavlink.MAV_STATE_UNINIT)

	def recvCb(self):
		# This callback will be running inside a Thread

		while (True):
			cmd = mavutil.mavlink.MAV_CMD_USER_1
			msg = self.mav.recv_match(blocking=True)
			if msg is not None:
				cmd_type = msg.get_type()
				src_sys = msg.get_srcSystem()
				msg_tgt = msg.target_system
				if cmd_type == "COMMAND_LONG" and src_sys > 0 and src_sys <= self.n and msg.command == cmd and msg_tgt == self.master_sys_id:

					if msg.param1 == self.ROBOT_STATE:
						if self.DEBUG:
							rospy.logwarn("[Master]: Received ROBOT_STATE from Robot %s", src_sys-1)
						state_msg = RobotFormationState()
						state_msg.header.stamp		= rospy.Time.now()
						state_msg.received_goal		= msg.param2
						state_msg.mission_started	= msg.param3
						state_msg.arrived			= msg.param4
						state_msg.point.x			= msg.param5
						state_msg.point.y			= msg.param6
						state_msg.point.z			= msg.param7

						# publish msg to ROS
						self.robot_state_pub_list[src_sys-1].publish(state_msg)

					if msg.param1 == self.MASTER_CMD_ACK:
						rospy.logwarn("[Master]: Got acknowledgment of %s from robot %s", self.CMD_STRING[msg.param2], src_sys-1)

				else:
					if self.DEBUG:
						rospy.logwarn("Received unexpected MAVLink msg of type: %s from MAVLink ID = %s", msg.get_type(), msg.get_srcSystem())

			# Should we sleep before we poll the udp again?
			sleep(0.02)


	##### Callbacks ###

	def goCb(self, msg):
		tgt_sys = 0 # to all
		tgt_comp_id = 0
		p1 = self.MASTER_CMD
		p2 = self.MASTER_CMD_GO
		p3, p4, p5, p6, p7 = 0, 0, 0, 0, 0
		self.mav.mav.command_long_send(tgt_sys, tgt_comp_id, mavutil.mavlink.MAV_CMD_USER_1, 0, p1, p2, p3, p4, p5, p6, p7)

		if self.DEBUG:
			rospy.logwarn("[Master]: Sent MASTER_CMD_GO to all systems")

	def formationCb(self, msg):

		tgt_comp_id = 0
		for i in range(self.n):
			tgt_sys = i+1
			p1 = self.MASTER_CMD
			p2 = self.MASTER_CMD_GOAL
			p3 = msg.goals[i].x
			p4 = msg.goals[i].y
			p5 = msg.goals[i].z
			p6 = msg.tf
			p7 = 0
			self.mav.mav.command_long_send(tgt_sys, tgt_comp_id, mavutil.mavlink.MAV_CMD_USER_1, 0, p1, p2, p3, p4, p5, p6, p7)

			if self.DEBUG:
				rospy.logwarn("[Master]: Sent formation goal to Robot %s", i)

			sleep(0.01)


	def nRCb(self, msg):
		r_id = 0 # to all
		nR = msg.data
		tgt_comp_id = 0
		p1 = self.MASTER_CMD
		p2 = self.MASTER_CMD_SET_nROBOTS
		p3 = nR # number of robots
		p4, p5, p6, p7 = 0, 0, 0, 0
		self.mav.mav.command_long_send(r_id, tgt_comp_id, mavutil.mavlink.MAV_CMD_USER_1, 0, p1, p2, p3, p4, p5, p6, p7)

		if self.DEBUG:
			rospy.logwarn("[Master]: sending number of robots = %s to all robots", nR)

	def setOriginCb(self, msg):
		r_id = 0
		tgt_comp_id = 0
		p1 = self.MASTER_CMD
		p2 = self.MASTER_CMD_SET_ORIGIN
		p3 = msg.x 
		p4 = msg.y
		p5 = msg.z
		p6, p7 = 0, 0
		self.mav.mav.command_long_send(r_id, tgt_comp_id, mavutil.mavlink.MAV_CMD_USER_1, 0, p1, p2, p3, p4, p5, p6, p7)

		if self.DEBUG:
			rospy.logwarn("[Master]: sending Origin coordinates to all robots")

	def setEastCb(self, msg):
		r_id = 0
		tgt_comp_id = 0
		p1 = self.MASTER_CMD
		p2 = self.MASTER_CMD_SET_EAST
		p3 = msg.x 
		p4 = msg.y
		p5 = msg.z
		p6, p7 = 0, 0
		self.mav.mav.command_long_send(r_id, tgt_comp_id, mavutil.mavlink.MAV_CMD_USER_1, 0, p1, p2, p3, p4, p5, p6, p7)

		if self.DEBUG:
			rospy.logwarn("[Master]: sending East coordinates to all robots")

	def setTOALTCb(self, msg):
		if msg is not None:
			r_id = 0
			tgt_comp_id = 0
			p1 = self.MASTER_CMD
			p2 = self.MASTER_CMD_SET_TOALT
			p3 = msg.data
			p4, p5, p6, p7 = 0, 0, 0, 0
			self.mav.mav.command_long_send(r_id, tgt_comp_id, mavutil.mavlink.MAV_CMD_USER_1, 0, p1, p2, p3, p4, p5, p6, p7)

			if self.DEBUG:
				rospy.logwarn("[Master]: sending TOALT=%s to all robots", msg.data)

	def armCb(self, msg):
		r_id = msg.data
		tgt_comp_id = 0
		p1 = self.MASTER_CMD
		p2 = self.MASTER_CMD_ARM
		p3 = 1 # 1: arm, 0: disarm
		p4, p5, p6, p7 = 0, 0, 0, 0
		self.mav.mav.command_long_send(r_id, tgt_comp_id, mavutil.mavlink.MAV_CMD_USER_1, 0, p1, p2, p3, p4, p5, p6, p7)

		if self.DEBUG:
			if r_id > 0:
				rospy.logwarn("[Master]: sending CMD_ARM to robot with MAVLink ID = %s", r_id)
			else:
				rospy.logwarn("[Master]: sending CMD_ARM to all robots")

	def disarmCb(self, msg):
		r_id = msg.data
		tgt_comp_id = 0
		p1 = self.MASTER_CMD
		p2 = self.MASTER_CMD_ARM
		p3 = 0 # 1: arm, 0: disarm
		p4, p5, p6, p7 = 0, 0, 0, 0
		self.mav.mav.command_long_send(r_id, tgt_comp_id, mavutil.mavlink.MAV_CMD_USER_1, 0, p1, p2, p3, p4, p5, p6, p7)

		if self.DEBUG:
			if r_id > 0:
				rospy.logwarn("[Master]: sending CMD_DISARM to robot with MAVLink ID = %s", r_id)
			else:
				rospy.logwarn("[Master]: sending CMD_DISARM to all robots")

	def tkoCb(self, msg):
		r_id = msg.data
		tgt_comp_id = 0
		p1 = self.MASTER_CMD
		p2 = self.MASTER_CMD_TKO
		p3, p4, p5, p6, p7 = 0, 0, 0, 0, 0
		self.mav.mav.command_long_send(r_id, tgt_comp_id, mavutil.mavlink.MAV_CMD_USER_1, 0, p1, p2, p3, p4, p5, p6, p7)

		if self.DEBUG:
			if r_id > 0:
				rospy.logwarn("[Master]: sending CMD_TAKEOFF to robot with MAVLink ID = %s", r_id)
			else:
				rospy.logwarn("[Master]: sending CMD_TAKEOFF to all robots")

	def landCb(self, msg):
		r_id = msg.data
		tgt_comp_id = 0
		p1 = self.MASTER_CMD
		p2 = self.MASTER_CMD_LAND
		p3, p4, p5, p6, p7 = 0, 0, 0, 0, 0
		self.mav.mav.command_long_send(r_id, tgt_comp_id, mavutil.mavlink.MAV_CMD_USER_1, 0, p1, p2, p3, p4, p5, p6, p7)

		if self.DEBUG:
			if r_id > 0:
				rospy.logwarn("[Master]: sending CMD_LAND to robot with MAVLink ID = %s", r_id)
			else:
				rospy.logwarn("[Master]: sending CMD_LAND to all robots")

	def holdCb(self, msg):
		r_id = msg.data
		tgt_comp_id = 0
		p1 = self.MASTER_CMD
		p2 = self.MASTER_CMD_HOLD
		p3, p4, p5, p6, p7 = 0, 0, 0, 0, 0
		self.mav.mav.command_long_send(r_id, tgt_comp_id, mavutil.mavlink.MAV_CMD_USER_1, 0, p1, p2, p3, p4, p5, p6, p7)

		if self.DEBUG:
			if r_id > 0:
				rospy.logwarn("[Master]: sending CMD_HOLD to robot with MAVLink ID = %s", r_id)
			else:
				rospy.logwarn("[Master]: sending CMD_HOLD to all robots")

	def posctlCb(self, msg):
		r_id = msg.data
		tgt_comp_id = 0
		p1 = self.MASTER_CMD
		p2 = self.MASTER_CMD_POSCTL
		p3, p4, p5, p6, p7 = 0, 0, 0, 0, 0
		self.mav.mav.command_long_send(r_id, tgt_comp_id, mavutil.mavlink.MAV_CMD_USER_1, 0, p1, p2, p3, p4, p5, p6, p7)

		if self.DEBUG:
			if r_id > 0:
				rospy.logwarn("[Master]: sending CMD_POSCTL to robot with MAVLink ID = %s", r_id)
			else:
				rospy.logwarn("[Master]: sending CMD_POSCTL to all robots")

	def shutdownCb(self, msg):
		r_id = msg.data
		tgt_comp_id = 0
		p1 = self.MASTER_CMD
		p2 = self.MASTER_CMD_SHUTDOWN
		p3, p4, p5, p6, p7 = 0, 0, 0, 0, 0
		self.mav.mav.command_long_send(r_id, tgt_comp_id, mavutil.mavlink.MAV_CMD_USER_1, 0, p1, p2, p3, p4, p5, p6, p7)

		if self.DEBUG:
			if r_id > 0:
				rospy.logwarn("[Master]: sending CMD_SHUTDOWN to robot with MAVLink ID = %s", r_id)
			else:
				rospy.logwarn("[Master]: sending CMD_SHUTDOWN to all robots")

	def rebootCb(self, msg):
		r_id = msg.data
		tgt_comp_id = 0
		p1 = self.MASTER_CMD
		p2 = self.MASTER_CMD_REBOOT
		p3, p4, p5, p6, p7 = 0, 0, 0, 0, 0
		self.mav.mav.command_long_send(r_id, tgt_comp_id, mavutil.mavlink.MAV_CMD_USER_1, 0, p1, p2, p3, p4, p5, p6, p7)

		if self.DEBUG:
			if r_id > 0:
				rospy.logwarn("[Master]: sending CMD_REBOOT to robot with MAVLink ID = %s", r_id)
			else:
				rospy.logwarn("[Master]: sending CMD_REBOOT to all robots")

def main():
	rospy.init_node('master_mavlink_node', anonymous=True)

	rospy.logwarn("Starting master_mavlink_node")

	M = MasterBridge()

	# Run recevCb in a thread
	recvthread = Thread(target=M.recvCb)
	recvthread.daemon = True
	recvthread.start()

	# ROS loop frequency, Hz
	rate = rospy.Rate(2.0)

	while not rospy.is_shutdown():

		if M.ENABLE_MASTER_GCS:
			M.send_heartbeat()

		rate.sleep()

if __name__ == '__main__':
	try:
		main()
	except rospy.ROSInterruptException:
		pass

