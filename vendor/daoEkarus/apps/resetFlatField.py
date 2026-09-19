#!/usr/bin/env python3
#
import dao
import daoEkarusShmNames as shm_names

ff = dao.shm(shm_names.SHM_OCAM_FLAT_FIELD)
ff.set_data(ff.get_data() * 0 + 1.0)
