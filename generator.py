#!/bin/bash


##
# 


COUNTRYCODE = "00233" #Ghana

PREFIX = [
    24, #MTN
    54  #MTN
]

LENGTH_AFTER_PREFIX = 7

for p in PREFIX:
    for r in range((10 ** LENGTH_AFTER_PREFIX ) - 1):
       print "{0}{1}{2}".format(str(COUNTRYCODE), str(p), str(r).zfill(LENGTH_AFTER_PREFIX))
