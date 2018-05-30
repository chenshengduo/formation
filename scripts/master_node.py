#!/usr/bin/env python

import rospy # ROS interface
import pymap3d as pm # coordinate conversion

# msgs
from formation.msg import RobotState, FormationPositions
from std_msgs.msg import Empty
from geometry_msgs.msg import Point, PointStamped
from sensor_msgs.msg import NavSatFix
from mavros_msgs.msg import *

# math
from math import atan2, cos, sin

# To calculate execution time
import time

# for matrix operation
import numpy as np

# To compute distance matrix
from scipy.spatial import distance

# faster linear sum assignment solver: https://github.com/gatagat/lap
# pip install lap
from lap import lapjv

class Mission:
	def __init__(self):
		# number of robots
		self.n 			= rospy.get_param("nRobots", 5)
		# robot's radius
		self.R			= rospy.get_param("R", 0.5)
		# safety distance
		self.delta		= 2.0*(2**0.5)*self.R
		# max robot's velocity
		self.vmax		= rospy.get_param("vmax", 1.0)

		self.origin		= rospy.get_param("origin", [10.12345, 20.12345])
		self.east		= rospy.get_param("east", [10.12345, 20.12345])

		# formation: start position nx3 array
		self.P			= np.zeros((self.n,3))
		# formation: desired shape positions
		self.S			= rospy.get_param("shape")
		self.S_array	= np.array(self.S)
		# formation: goal positions nx3 array
		self.G			= np.zeros((self.n,3))

		# current robot positions nx3
		self.current_P	= np.zeros((self.n,3))

		# Assigned goals & completion time
		self.goals_msg 	= FormationPositions()
		p = Point(0.0, 0.0, 0.0)
		for i in range(self.n):
			self.goals_msg.goals.append(p)

		# arrival (to goals) state for all robots
		self.arrival_state = self.n*[False]

		# if all each robot received assigned goal
		self.received_goals = self.n*[False]

		# True if all robots arrived at their goals
		# True if all elements in self.arrival_state are True
		self.formation_completed = False

		# Mission flags

		# true if P & S are valid
		self.valid_P		= False
		self.valid_S		= False

		self.P_is_set		= False
		self.S_is_set		= False

		self.G_is_set		= False

		self.M_START		= False
		self.M_END			= False


		# Topics names of robots locations in local defined ENU coordiantes
		self.r_loc_topic_names = []
		rstr = "/robot"
		for i in range(self.n):
			self.r_loc_topic_names.append(rstr+str(i)+"/state")


	def validate_positions(self):
		self.valid_P = True
		self.valid_S = True
		for i in range(self.n):
			if not self.valid_P:
				break

			for j in range(self.n):
				if i != j:
					if np.linalg.norm(self.P[i,:] - self.P[j,:]) <= self.delta:
						self.valid_P = False
						rospy.logwarn("Robots %s and %s are not well seperated", i,j)
						break

		for i in range(self.n):
			if not self.valid_S:
				break

			for j in range(self.n):
				if i != j:
					if np.linalg.norm(self.S_array[i,:] - self.S_array[j,:]) <= self.delta:
						self.valid_S = False
						rospy.logwarn("Goals %s and %s are not well seperated", i,j)
						break

	def compute_assignment(self):
		# compute sudo cost
		K = -1.0*np.dot(self.P,np.transpose(self.S_array))

		#find optimal assignment LSA
		rospy.logwarn("Solving Assignement Problem....")
		t1 = time.time()
		k_opt, x,y = lapjv(K)
		t2 = time.time()
		rospy.logwarn("Assignment is solved in %s seconds", t2-t1)

		# set goals
		tf = 0.0
		for i in range(self.n):
			self.G[i,:] = self.S_array[x[i],:]
			p = Point(self.G[i,0], self.G[i,1], self.G[i,2])
			self.goals_msg.goals[i] = p

			v = np.linalg.norm(self.P[i,:] - self.G[i,:])/self.vmax
			if v > tf:
				tf = v

		# set completion time, tf
		self.goals_msg.tf = tf
		# update time stamp
		self.goals_msg.header.stamp = rospy.Time.now()

		self.G_is_set = True

	################# Callbacks
	def r0Cb(self, msg):
		i=0
		p = np.array([msg.point.x, msg.point.y, msg.point.z])
		self.current_P[i,:] = p
		self.arrival_state[i] = msg.arrived
		self.received_goals[i] = msg.received_goal

	def r1Cb(self, msg):
		i=1
		p = np.array([msg.point.x, msg.point.y, msg.point.z])
		self.current_P[i,:] = p
		self.arrival_state[i] = msg.arrived
		self.received_goals[i] = msg.received_goal

	def r2Cb(self, msg):
		i=2
		p = np.array([msg.point.x, msg.point.y, msg.point.z])
		self.current_P[i,:] = p
		self.arrival_state[i] = msg.arrived
		self.received_goals[i] = msg.received_goal
		
	def r3Cb(self, msg):
		i=3
		p = np.array([msg.point.x, msg.point.y, msg.point.z])
		self.current_P[i,:] = p
		self.arrival_state[i] = msg.arrived
		self.received_goals[i] = msg.received_goal

	def r4Cb(self, msg):
		i=4
		p = np.array([msg.point.x, msg.point.y, msg.point.z])
		self.current_P[i,:] = p
		self.arrival_state[i] = msg.arrived
		self.received_goals[i] = msg.received_goal

	def set_start_posCb(self):
		"""Sets starting position from robot current position
		"""
		self.P = np.copy(self.current_P)
		self.P_is_set = True

	def set_desired_formation(self):
		"""gets desired formation from shape.yaml in config folder
		"""
		self.S = rospy.get_param("shape")
		self.S_array = np.array(self.S)
		self.S_is_set = True

	def startCb(self, msg):
		if self.M_START:
			rospy.logwarn("Mission already started!")
		else:
			self.set_start_posCb()
			self.set_desired_formation()
			self.validate_positions()
			if self.valid_S and valid_P:
				self.compute_assignment()
				self.M_START = True

	def landCb(self, msg):
		# reset flags
		self.M_START = False
		self.P_is_set = False
		self.S_is_set = False
		self.G_is_set = False

	def holdCb(self, msg):
		# reset flags
		self.M_START = False
		self.P_is_set = False
		self.S_is_set = False
		self.G_is_set = False

	def isFormationComplete(self):
		self.formation_completed = all(self.arrival_state)
		return self.formation_completed

def main():
	
	rospy.init_node('formation_master_node', anonymous=True)

	rospy.logwarn("Started Master Node.")

	M = Mission()

	# Subscribers: Robots states
	rospy.Subscriber(M.r_loc_topic_names[0], RobotState, M.r0Cb)
	rospy.Subscriber(M.r_loc_topic_names[1], RobotState, M.r1Cb)
	rospy.Subscriber(M.r_loc_topic_names[2], RobotState, M.r2Cb)
	rospy.Subscriber(M.r_loc_topic_names[3], RobotState, M.r3Cb)
	rospy.Subscriber(M.r_loc_topic_names[4], RobotState, M.r4Cb)

	# Subscriber: start flag
	rospy.Subscriber("/start", Empty, M.startCb)
	#Subscriber: land/hold
	rospy.Subscriber("/land", Empty, M.landCb)
	rospy.Subscriber("/hold", Empty, M.holdCb)

	# Publisher: Formation goals & tf
	form_pub = rospy.Publisher("/formation", FormationPositions, queue_size=1)
	# Publisher: GO signal
	go_pub = rospy.Publisher("/go", Empty, queue_size=1)
	go_msg = Empty()

	rate = rospy.Rate(10.0)

	while not rospy.is_shutdown():

		if M.M_START:
			M.M_END = False
			if not all(M.received_goals):
				form_pub.publish(M.goals_msg)
			else:
				go_pub.publish(go_msg)
		if M.isFormationComplete():
			M.M_END = True
			M.M_START = False
			M.P_is_set = False
			M.S_is_set = False
			M.G_is_set = False

		rate.sleep()


if __name__ == '__main__':
	try:
		main()
	except rospy.ROSInterruptException:
		pass