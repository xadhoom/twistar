from twisted.internet import defer

## props will be one of:
## 1) A dict, in which case return an instance of klass
## 2) A list of dicts, in which case return a list of klasses
## The result will be wrapped in a deferred
def createInstances(props, klass):
    result = None
    if type(props) is list:
        result = [klass(**prop) for prop in props]
    elif props is not None:
        result = klass(**props)
    return defer.succeed(result)

                            
def joinWheres(self, wone, wtwo, joiner="AND"):
    statement = ["%s %s %s" % (wone[0], joiner, wtwo[0])]
    args = wone[1:] + wtwo[1:]
    return statement + args
                
