"""
Base module for interfacing with databases.
"""
import sys

from twisted.python import log

from twisted.internet import reactor, threads

from twistar.registry import Registry        
from twistar.exceptions import ImaginaryTableError, TransactionNotStartedError

class InteractionBase:
    """
    Class that specific database implementations extend.

    @cvar LOG: If True, then all queries are logged using C{twisted.python.log.msg}.

    @cvar includeBlankInInsert: If True, then insert/update queries will include
    setting object properties that have not be set to null in their respective columns.
    """
    
    LOG = False
    includeBlankInInsert = True

    
    def log(self, query, args, kwargs):
        """
        Log the query and any args or kwargs using C{twisted.python.log.msg} if
        C{InteractionBase.LOG} is True.
        """
        if not InteractionBase.LOG:
            return
        log.msg("TWISTAR query: %s" % query)
        if len(args) > 0:
            log.msg("TWISTAR args: %s" % ",".join(map(lambda x: str(x), *args)))
        elif len(kwargs) > 0:
            log.msg("TWISTAR kargs: %s" % str(kwargs))        


    def executeOperation(self, query, *args, **kwargs):
        """
        Simply makes same C{twisted.enterprise.dbapi.ConnectionPool.runOperation} call, but
        with call to L{log} function.
        """
        self.log(query, args, kwargs)
        return Registry.DBPOOL.runOperation(query, *args, **kwargs)


    def execute(self, query, *args, **kwargs):
        """
        Simply makes same C{twisted.enterprise.dbapi.ConnectionPool.runQuery} call, but
        with call to L{log} function.
        """        
        self.log(query, args, kwargs)
        return Registry.DBPOOL.runQuery(query, *args, **kwargs)


    def startTxn(self):
        """
	Start a transaction. 

	@return: a C{dict} containing a C{t.e.a.Transaction} and C{t.e.a.Connection} instances
        """    
	txn = None
	connection = Registry.DBPOOL.connectionFactory(Registry.DBPOOL)
	txn = Registry.DBPOOL.transactionFactory(Registry.DBPOOL, connection])	
	return txn


    def executeTxn(self, txn, query, *args, **kwargs):
        """
        Execute given query within the given transaction.  Also, makes call
        to L{log} function.
        """        
        self.log(query, args, kwargs)
        return txn.execute(query, *args, **kwargs)


    def select(self, tablename, id=None, where=None, group=None, limit=None, orderby=None, select=None):
        """
        Select rows from a table.

        @param tablename: The tablename to select rows from.

        @param id: If given, only the row with the given id will be returned (or C{None} if not found).

        @param where: Conditional of the same form as the C{where} parameter in L{DBObject.find}.

        @param group: String describing how to group results.

        @param limit: Integer limit on the number of results.  If this value is 1, then the result
        will be a single dictionary.  Otherwise, if C{id} is not specified, an array will be returned.
        This can also be a tuple, where the first value is the integer limit and the second value is
        an integer offset.  In the case that an offset is specified, an array will always be returned.

        @param orderby: String describing how to order the results.

        @param select: Columns to select.  Default is C{*}.

        @return: If C{limit} is 1 or id is set, then the result is one dictionary or None if not found.
        Otherwise, an array of dictionaries are returned.
        """
        one = False
        select = select or "*"
        
        if id is not None:
            where = ["id = ?", id]
            one = True

        if not isinstance(limit, tuple) and limit is not None and int(limit) == 1:
            one = True
            
        q = "SELECT %s FROM %s" % (select, tablename)
        args = []
        if where is not None:
            wherestr, args = self.whereToString(where)
            q += " WHERE " + wherestr
        if group is not None:
            q += " GROUP BY " + group
        if orderby is not None:
            q += " ORDER BY " + orderby
            
        if isinstance(limit, tuple):
            q += " LIMIT %s OFFSET %s" % (limit[0], limit[1])
        elif limit is not None:
            q += " LIMIT " + str(limit)
            
        return Registry.DBPOOL.runInteraction(self._doselect, q, args, tablename, one)


    def _doselect(self, txn, q, args, tablename, one=False):
        """
        Private callback for actual select query call.
        """
        self.executeTxn(txn, q, args)

        if one:
            result = txn.fetchone()
            if not result:
                return None
            vals = self.valuesToHash(txn, result, tablename)
            return vals

        results = []
        for result in txn.fetchall():
            vals = self.valuesToHash(txn, result, tablename)
            results.append(vals)            
        return results
    

    def insertArgsToString(self, vals):
        """
        Convert C{{'name': value}} to an insert "values" string like C{"(%s,%s,%s)"}.
        """
        return "(" + ",".join(["%s" for _ in vals.items()]) + ")"


    def insert(self, tablename, vals, txn=None):
        """
        Insert a row into the given table.

        @param tablename: Table to insert a row into.
        
        @param vals: Values to insert.  Should be a dictionary in the form of
        C{{'name': value, 'othername': value}}.

        @param txn: If txn is given it will be used for the query,
        otherwise a typical runQuery will be used

        @return: A C{Deferred} that calls a callback with the id of new row.
        """
        params = self.insertArgsToString(vals)
        colnames = ""
        if len(vals) > 0:
            ecolnames = self.escapeColNames(vals.keys())
            colnames = "(" + ",".join(ecolnames) + ")"
            params = "VALUES %s" % params
        q = "INSERT INTO %s %s %s" % (tablename, colnames, params)
        if not txn is None:
            return self.executeTxn(txn, q, vals.values())
        return self.executeOperation(q, vals.values())


    def escapeColNames(self, colnames):
        """
        Escape column names for insertion into SQL statement.

        @param colnames: A C{List} of string column names.

        @return: A C{List} of string escaped column names.
        """
        return map(lambda x: "`%s`" % x, colnames)


    def insertMany(self, tablename, vals):
        """
        Insert many values into a table.

        @param tablename: Table to insert a row into.
        
        @param vals: Values to insert.  Should be a list of dictionaries in the form of
        C{{'name': value, 'othername': value}}.

        @return: A C{Deferred}.
        """
        colnames = ",".join(self.escapeColNames(vals[0].keys()))
        params = ",".join([self.insertArgsToString(val) for val in vals])
        args = []
        for val in vals:
            args = args + val.values()
        q = "INSERT INTO %s (%s) VALUES %s" % (tablename, colnames, params)
        return self.executeOperation(q, args)
        

    def getLastInsertID(self, txn):
        """
        Using the given txn, get the id of the last inserted row.

        @return: The integer id of the last inserted row.
        """
        q = "SELECT LAST_INSERT_ID()"
        self.executeTxn(txn, q)            
        result = txn.fetchall()
        return result[0][0]
    

    def delete(self, tablename, where=None, txn=None):
        """
        Delete from the given tablename.

        @param where: Conditional of the same form as the C{where} parameter in L{DBObject.find}.
        If given, the rows deleted will be restricted to ones matching this conditional.

        @param txn: If txn is given it will be used for the query,
        otherwise a typical runQuery will be used

        @return: A C{Deferred}.        
        """
        q = "DELETE FROM %s" % tablename
        args = []
        if where is not None:
            wherestr, args = self.whereToString(where)
            q += " WHERE " + wherestr
        if txn is not None:
            return self.executeTxn(txn, q, args)
        return self.executeOperation(q, args)


    def update(self, tablename, args, where=None, txn=None):
        """
        Update a row into the given table.

        @param tablename: Table to insert a row into.
        
        @param args: Values to insert.  Should be a dictionary in the form of
        C{{'name': value, 'othername': value}}.

        @param where: Conditional of the same form as the C{where} parameter in L{DBObject.find}.
        If given, the rows updated will be restricted to ones matching this conditional.        

        @param txn: If txn is given it will be used for the query,
        otherwise a typical runQuery will be used

        @return: A C{Deferred}
        """
        setstring, args = self.updateArgsToString(args)
        q = "UPDATE %s " % tablename + " SET " + setstring
        if where is not None:
            wherestr, whereargs = self.whereToString(where)
            q += " WHERE " + wherestr
            args += whereargs
            
        if txn is not None:
            return self.executeTxn(txn, q, args)
        return self.executeOperation(q, args)


    def valuesToHash(self, txn, values, tablename):
        """
        Given a row from a database query (values), create
        a hash using keys from the table schema and values from
        the given values;

        @param txn: The transaction to use for the schema update query.

        @param values: A row from a db (as a C{list}).

        @param tablename: Name of the table to fetch the schema for.
        """
        cols = [row[0] for row in txn.description]
        if not Registry.SCHEMAS.has_key(tablename):
            Registry.SCHEMAS[tablename] = cols
        h = {}
        for index in range(len(values)):
            colname = cols[index]
            h[colname] = values[index]
        return h


    def getSchema(self, tablename, txn=None):
        """
        Get the schema (in the form of a list of column names) for
        a given tablename.  Use the given transaction if specified.
        """
        if not Registry.SCHEMAS.has_key(tablename) and txn is not None:
            try:
                self.executeTxn(txn, "SELECT * FROM %s LIMIT 1" % tablename)
            except Exception, e:
                raise ImaginaryTableError, "Table %s does not exist." % tablename
            Registry.SCHEMAS[tablename] = [row[0] for row in txn.description]
        return Registry.SCHEMAS.get(tablename, [])
            

    def insertObj(self, obj):
        """
        Insert the given object into its table.

        @return: A C{Deferred} that sends a callback the inserted object.
        """
        def _doinsert(txn):
            klass = obj.__class__
            tablename = klass.tablename()
            cols = self.getSchema(tablename, txn)
            if len(cols) == 0:
                raise ImaginaryTableError, "Table %s does not exist." % tablename
            vals = obj.toHash(cols, includeBlank=self.__class__.includeBlankInInsert, exclude=['id'])
            self.insert(tablename, vals, txn)
            obj.id = self.getLastInsertID(txn)
            return obj
	if obj._txn is not None:
        	return self.runWithTransaction(_doinsert, obj._txn)
	else:
        	return Registry.DBPOOL.runInteraction(_doinsert)


    def updateObj(self, obj):
        """
        Update the given object's row in the object's table.

        @return: A C{Deferred} that sends a callback the updated object.
        """        
        def _doupdate(txn):
            klass = obj.__class__
            tablename = klass.tablename()
            cols = self.getSchema(tablename, txn)
            
            vals = obj.toHash(cols, exclude=['id'])
            return self.update(tablename, vals, where=['id = ?', obj.id], txn=txn)
        # We don't want to return the cursor - so add a blank callback returning the obj
	if obj._txn is not None:
        	return self.runWithTransaction(_doupdate, obj._txn).addCallback(lambda _: obj)
	else:
        	return Registry.DBPOOL.runInteraction(_doupdate).addCallback(lambda _: obj)    


    def refreshObj(self, obj):
        """
        Update the given object based on the information in the object's table.

        @return: A C{Deferred} that sends a callback the updated object.
        """                
        def _dorefreshObj(newobj):
            if obj is None:
                raise CannotRefreshError, "Can't refresh object if id not longer exists."
            for key in newobj.keys():
                setattr(obj, key, newobj[key])
        return self.select(obj.tablename(), obj.id).addCallback(_dorefreshObj)


    def whereToString(self, where):
        """
        Convert a conditional to the form needed for a query using the DBAPI.  For instance,
        for most DB's question marks in the query string have to be converted to C{%s}.  This
        will vary by database.

        @param where: Conditional of the same form as the C{where} parameter in L{DBObject.find}.

        @return: A conditional in the same form as the C{where} parameter in L{DBObject.find}.
        """
        assert(type(where) is list)
        query = where[0].replace("?", "%s")
        args = where[1:]
        return (query, args)


    def updateArgsToString(self, args):
        """
        Convert dictionary of arguments to form needed for DB update query.  This method will
        vary by database driver.
        
        @param args: Values to insert.  Should be a dictionary in the form of
        C{{'name': value, 'othername': value}}.

        @return: A tuple of the form C{('name = %s, othername = %s, ...', argvalues)}.
        """
        colnames = self.escapeColNames(args.keys())
        setstring = ",".join([key + " = %s" for key in colnames])
        return (setstring, args.values())

    
    def commit(self, obj):
	"""
	Commits current obj transaction.

        @return: A C{Deferred}
	"""
	return threads.deferToThreadPool(reactor, Registry.DBPOOL.threadpool, self._commit, obj._txn)


    def _commit(self, transaction):
       	trans = transaction['transaction']
	conn = trans._connection

	if trans._cursor is None:
		raise TransactionNotStartedError("Cannot call commit without a transaction")

	try:
		trans.close()
		conn.commit()
	except:
        	excType, excValue, excTraceback = sys.exc_info()
		try:
			conn.rollback()
		except:
			log.err(None, "Rollback failed")
		raise excType, excValue, excTraceback


    def rollback(self, obj):
	"""
	Rollback current obj transaction.

        @return: A C{Deferred}
	"""
	return threads.deferToThreadPool(reactor, Registry.DBPOOL.threadpool, self._rollback, obj._txn)


    def _rollback(self, transaction):
       	trans = transaction['transaction']
	conn = trans._connection

	if trans._cursor is None:
		raise TransactionNotStartedError("Cannot call rollback without a transaction")

	try:
		trans.close()
		conn.rollback()
	except:
        	excType, excValue, excTraceback = sys.exc_info()
		raise excType, excValue, excTraceback


    def runWithTransaction(self, interaction, transaction, *args, **kw):
	"""
	Interact with the database and return the result, using the given transaction and connection.
	Inspired from twisted.enterprise.adbapi.ConnectionPool.runInteraction

	The 'interaction' is a callable object which will be executed in a thread using a pooled connection. 
	It will be passed an C{Transaction} object as an argument (whose interface is identical to that of 
	the database cursor for your DB-API module of choice), and its results will be returned as a Deferred. 
	If running the method raises an exception, the transaction will NOT be rolled back. 
	The transaction will NOT be committed automatically, you have to call commit on the transaction.

	NOTE that the function you pass is *not* run in the main thread: you may have to worry 
 	about thread-safety in the function you pass to this if it tries to use non-local objects.

	@param interaction: a callable object whose first argument
	    is an L{adbapi.Transaction}.

	@param transaction: a C {dict} containing containing a C{t.e.a.Transaction} and C{t.e.a.Connection} instances

	@param *args: additional positional arguments to be passed
	    to interaction

	@param **kw: keyword arguments to be passed to interaction

	@return: a Deferred which will fire the return value of
	    'interaction(Transaction(...), *args, **kw)', or a Failure.

	"""
	return threads.deferToThreadPool(reactor, Registry.DBPOOL.threadpool,
					 self._runWithTransaction,
					 interaction, transaction, *args, **kw)


    def _runWithTransaction(self, interaction, transaction, *args, **kw):
       	trans = transaction['transaction']
	conn = trans._connection

	if trans._cursor is None:
		raise TransactionNotStartedError("Cannot call transaction without a transaction")

	try:
		result = interaction(trans, *args, **kw)
		return result
	except:
        	excType, excValue, excTraceback = sys.exc_info()
		# conn.rollback here?
		raise excType, excValue, excTraceback


