#!/usr/bin/env python3
#
import dao
import sys
from daoEkarusShmNames import *

dmFlat = dao.shm(sys.argv[1])
# applys flat
dmFlat.set_data(dmFlat.get_data() * 0)
