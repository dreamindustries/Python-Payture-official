import logging
import xml.etree.ElementTree as ET

import requests

from payture import constants
from payture import paytureresponse


SUCCESS_MAP = {"True": True, "False": False, "3DS": False}
logger = logging.getLogger("payture.transaction")


class RequestClient(object):
    """Base class for posting request to Payture server"""

    def __init__(self):
        super(RequestClient, self).__init__()

    def _post(self, url, content):
        """Sync "POST" HTTP method for pass data to Payture"""
        logger.info("Request ({}): {}".format(url, content))
        r = requests.post(url, content)
        logger.info("Response: {}".format(r.text))
        return self._parseXMLResponse(r.text)

    def _parseXMLResponse(self, responseBody):
        """Helper method for parsing received response (that in XML format)

        for API Methods: Charge/UnBlock/Refund/GetState
        for Ewallet and InPay Methods: Charge/UnBlock/Refund/PayStatus

        Keyword parameters:
        responseBody -- String representation of response body

        Return value:
        Return PaytureResponse object

        """

        root = ET.fromstring(responseBody)
        logger.info("Response root attributes: {}".format(root.attrib))
        for child in root:
            logger.info("Response child ({}): {}".format(child.tag, child.attrib))

        apiname = root.tag
        err = root.attrib.get("ErrCode")
        success = SUCCESS_MAP[root.attrib["Success"]]
        is_3ds = root.attrib["Success"] == "3DS"
        redirect_url = None
        session_id = root.attrib.get(constants.PaytureParams.SessionId)
        if success and apiname == "Init":
            redirect_url = "{}/{}/{}?{}={}".format(
                self._merchant.HOST,
                self._apiType,
                self._sessionType,
                constants.PaytureParams.SessionId,
                session_id,
            )
        response = paytureresponse.PaytureResponse(
            apiname, success, err, SessionId=session_id, RedirectURL=redirect_url, Is3DS=is_3ds,
        )
        return response


class Transaction(RequestClient):
    """Base class for transaction. Contains common fields used in request to Payture server, and common methods - available for all api type"""

    def __init__(self, api, command, merchant):
        self._apiType = api
        self._sessionType = constants.SessionType.Unknown
        self._merchant = merchant
        self._expanded = False
        self.Command = command
        self._requestKeyValuePair = {}
        super(Transaction, self).__init__()

    def expand(self, orderId, amount):
        """Expand transaction

        for API Methods: Charge/UnBlock/Refund/GetState
        for Ewallet and InPay Methods: Charge/UnBlock/Refund/PayStatus

        Keyword parameters:
        orderId -- Payment's identifier in Merchant system
        amount -- Payment's amount in kopec. Pass null for PayStatus and GetState commands

        Return value:
        Returns current expanded transaction

        """
        if self._expanded:
            return self
        if orderId == "":
            return self

        if self._apiType == constants.PaytureAPIType.vwapi:
            if self.Command == constants.PaytureCommands.PayStatus:
                self._requestKeyValuePair[
                    constants.PaytureParams.DATA
                ] = "{}={};".format(constants.PaytureParams.OrderId, orderId)
            elif (
                self.Command == constants.PaytureCommands.Refund and amount is not None
            ):
                self._requestKeyValuePair[
                    constants.PaytureParams.DATA
                ] = "{}={};{}={};{}={};".format(
                    constants.PaytureParams.OrderId,
                    orderId,
                    constants.PaytureParams.Amount,
                    amount,
                    constants.PaytureParams.Password,
                    self._merchant.Password,
                )
            elif amount is not None:
                self._requestKeyValuePair[constants.PaytureParams.Amount] = amount
            else:
                self._requestKeyValuePair[constants.PaytureParams.OrderId] = orderId
        else:
            self._requestKeyValuePair[constants.PaytureParams.OrderId] = orderId
            if amount is not None:
                self._requestKeyValuePair[constants.PaytureParams.Amount] = amount

        if self.Command == constants.PaytureCommands.Refund or (
            self._apiType != constants.PaytureAPIType.api
            and (
                self.Command == constants.PaytureCommands.Charge
                or self.Command == constants.PaytureCommands.Unblock
            )
        ):
            self._expandMerchant(True, True)
        else:
            self._expandMerchant()

        self._expanded = True
        return self

    def _expandMerchant(self, addKey=True, addPass=False):
        """ Expand transaction with Merchant key and password

        Keyword parameters:
        addKey -- pass False if Merchant key IS NOT NEEDED
        addPass -- pass true if Merchant password IS NEEDED

        Return value:
        Returns current expanded transaction

        """
        if addKey:
            self._requestKeyValuePair[
                (
                    constants.PaytureParams.VWID
                    if self._apiType == constants.PaytureAPIType.vwapi
                    else constants.PaytureParams.Key
                )
            ] = self._merchant.MerchantName
        if addPass:
            self._requestKeyValuePair[
                constants.PaytureParams.Password
            ] = self._merchant.Password
        return self

    def process(self):
        """ Process request to Payture server synchronously

        Return value:
        PaytureResponse - response from the Payture server. In case of exeption will be return PaytureResponse with exeption mesage in ErrCode field.

        """
        if not self._expanded:
            return paytureresponse.PaytureResponse.errorResponse(
                self.Command, "Params are not set"
            )
        return self._post(self.getPath(), self._requestKeyValuePair)

    def getPath(self):
        """Form URL as string for request"""
        return "{}/{}/{}".format(self._merchant.HOST, self._apiType, self.Command)
